use std::collections::{HashMap, HashSet};
use std::process::Stdio;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Json;
use serde::{Deserialize, Serialize};
use tokio::process::Command;
use tokio::sync::Mutex;
use tokio::time::timeout;

use crate::exec::{
    validate_cmd, ExecResult, EGRESS_PROXY, NO_PROXY, SANDBOX_NET, default_image, default_timeout,
};

/// One live sandbox container owned by a session.
pub struct SessionEntry {
    pub container: String,
    /// Last time a command ran inside the session; the reaper removes
    /// sessions idle longer than the TTL, so crashed runs can't leak.
    pub last_used: Instant,
}

/// session_id -> session. One container lives for the whole agent run:
/// every command runs inside it, and it is removed on delete or expiry.
pub type Sessions = Arc<Mutex<HashMap<String, SessionEntry>>>;

const CONTAINER_PREFIX: &str = "sandbox-session-";

fn default_ttl() -> Duration {
    Duration::from_secs(900)
}

fn default_reap_interval() -> Duration {
    Duration::from_secs(30)
}

fn env_duration(name: &str, default: Duration) -> Duration {
    std::env::var(name)
        .ok()
        .and_then(|v| v.parse::<u64>().ok())
        .map(Duration::from_secs)
        .unwrap_or(default)
}

#[derive(Debug, Deserialize)]
pub struct SessionCreateRequest {
    #[serde(default = "default_image")]
    pub image: String,
}

#[derive(Debug, Serialize)]
pub struct SessionCreateResponse {
    pub session_id: String,
}

#[derive(Debug, Deserialize)]
pub struct SessionExecRequest {
    pub cmd: String,
    #[serde(default = "default_timeout")]
    pub timeout_s: u64,
}

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn unique_session_id() -> String {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("{millis}-{n}")
}

async fn container_for(sessions: &Sessions, session_id: &str) -> Option<String> {
    sessions
        .lock()
        .await
        .get(session_id)
        .map(|entry| entry.container.clone())
}

fn expired_ids(entries: &HashMap<String, SessionEntry>, ttl: Duration) -> Vec<String> {
    entries
        .iter()
        .filter(|(_, entry)| entry.last_used.elapsed() >= ttl)
        .map(|(id, _)| id.clone())
        .collect()
}

/// Remove every `sandbox-session-*` docker container that is NOT currently
/// managed by a live gateway session (lost on crash/restart), plus all
/// sessions that expired. Runs on the first reaper tick and then on the
/// interval.
async fn reap_pass(sessions: &Sessions, ttl: Duration) {
    let expired: Vec<(String, String)> = {
        let guard = sessions.lock().await;
        expired_ids(&guard, ttl)
            .into_iter()
            .filter_map(|id| guard.get(&id).map(|entry| (id, entry.container.clone())))
            .collect()
    };
    for (session_id, container) in &expired {
        let _ = Command::new("docker")
            .args(["rm", "-f", container])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .await;
        sessions.lock().await.remove(session_id);
        tracing::info!(session_id, "reaped expired sandbox session");
    }

    let managed: HashSet<String> = {
        let guard = sessions.lock().await;
        guard.values().map(|entry| entry.container.clone()).collect()
    };
    let output = Command::new("docker")
        .args([
            "ps",
            "-a",
            "--filter",
            &format!("name={CONTAINER_PREFIX}"),
            "--format",
            "{{.Names}}",
        ])
        .output()
        .await;
    let Ok(output) = output else {
        return; // docker unavailable (tests, CI) - nothing to reap
    };
    if !output.status.success() {
        return;
    }
    for name in String::from_utf8_lossy(&output.stdout).lines() {
        let name = name.trim();
        if name.is_empty() || managed.contains(name) {
            continue;
        }
        let _ = Command::new("docker")
            .args(["rm", "-f", name])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .await;
        tracing::info!(container = name, "removed stale sandbox container");
    }
}

/// Background loop that keeps the container fleet clean. Spawned once from
/// `app()`; configurable via SANDBOX_SESSION_TTL_SECS (default 900) and
/// SANDBOX_REAP_INTERVAL_SECS (default 30).
pub fn start_reaper(sessions: Sessions) {
    let ttl = env_duration("SANDBOX_SESSION_TTL_SECS", default_ttl());
    let interval = env_duration("SANDBOX_REAP_INTERVAL_SECS", default_reap_interval());
    tokio::spawn(async move {
        let mut ticker = tokio::time::interval(interval);
        loop {
            ticker.tick().await;
            reap_pass(&sessions, ttl).await;
        }
    });
}

pub fn validate_exec(req: &SessionExecRequest) -> Result<(), String> {
    validate_cmd(&req.cmd, req.timeout_s)
}

pub async fn create_session_handler(
    State(sessions): State<Sessions>,
    Json(req): Json<SessionCreateRequest>,
) -> Result<Json<SessionCreateResponse>, (StatusCode, String)> {
    let session_id = unique_session_id();
    let container_name = format!("{CONTAINER_PREFIX}{session_id}");

    let mut args: Vec<String> = vec![
        "run".into(),
        "-d".into(),
        "--name".into(),
        container_name.clone(),
        "--network".into(),
        SANDBOX_NET.into(),
    ];
    for (key, value) in [
        ("HTTPS_PROXY", EGRESS_PROXY),
        ("HTTP_PROXY", EGRESS_PROXY),
        ("ALL_PROXY", EGRESS_PROXY),
        ("NO_PROXY", NO_PROXY),
    ] {
        args.push("-e".into());
        args.push(format!("{key}={value}"));
    }
    args.push(req.image);
    args.push("tail".into());
    args.push("-f".into());
    args.push("/dev/null".into());

    match Command::new("docker").args(&args).status().await {
        Ok(status) if status.success() => {
            sessions.lock().await.insert(
                session_id.clone(),
                SessionEntry {
                    container: container_name,
                    last_used: Instant::now(),
                },
            );
            Ok(Json(SessionCreateResponse { session_id }))
        }
        Ok(status) => Err((
            StatusCode::BAD_GATEWAY,
            format!("failed to create sandbox container: {status}"),
        )),
        Err(e) => Err((
            StatusCode::BAD_GATEWAY,
            format!("failed to run docker: {e}"),
        )),
    }
}

pub async fn exec_in_session_handler(
    State(sessions): State<Sessions>,
    Path(session_id): Path<String>,
    Json(req): Json<SessionExecRequest>,
) -> Result<Json<ExecResult>, (StatusCode, String)> {
    if let Err(e) = validate_exec(&req) {
        return Err((StatusCode::UNPROCESSABLE_ENTITY, e));
    }
    let Some(container) = container_for(&sessions, &session_id).await else {
        return Err((StatusCode::NOT_FOUND, format!("unknown session: {session_id}")));
    };
    sessions
        .lock()
        .await
        .get_mut(&session_id)
        .expect("session present from lookup")
        .last_used = Instant::now();

    let started = Instant::now();
    let child = match Command::new("docker")
        .args(["exec", &container, "sh", "-lc", &req.cmd])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(c) => c,
        Err(e) => {
            return Err((
                StatusCode::BAD_GATEWAY,
                format!("failed to exec in session: {e}"),
            ))
        }
    };

    match timeout(Duration::from_secs(req.timeout_s), child.wait_with_output()).await {
        Ok(Ok(output)) => Ok(Json(ExecResult {
            exit_code: output.status.code(),
            stdout: String::from_utf8_lossy(&output.stdout).to_string(),
            stderr: String::from_utf8_lossy(&output.stderr).to_string(),
            timed_out: false,
            duration_ms: started.elapsed().as_millis() as u64,
        })),
        Ok(Err(e)) => Err((StatusCode::BAD_GATEWAY, format!("failed to exec: {e}"))),
        Err(_) => {
            let _ = Command::new("docker")
                .args(["exec", &container, "pkill", "-9", "-f", &req.cmd])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
                .await;
            Ok(Json(ExecResult {
                exit_code: None,
                stdout: String::new(),
                stderr: "command timed out".to_string(),
                timed_out: true,
                duration_ms: started.elapsed().as_millis() as u64,
            }))
        }
    }
}

pub async fn delete_session_handler(
    State(sessions): State<Sessions>,
    Path(session_id): Path<String>,
) -> Result<StatusCode, (StatusCode, String)> {
    let Some(container) = container_for(&sessions, &session_id).await else {
        return Err((StatusCode::NOT_FOUND, format!("unknown session: {session_id}")));
    };

    match Command::new("docker")
        .args(["rm", "-f", &container])
        .status()
        .await
    {
        Ok(status) if status.success() => {
            sessions.lock().await.remove(&session_id);
            Ok(StatusCode::NO_CONTENT)
        }
        Ok(status) => Err((
            StatusCode::BAD_GATEWAY,
            format!("failed to remove sandbox container: {status}"),
        )),
        Err(e) => Err((
            StatusCode::BAD_GATEWAY,
            format!("failed to run docker: {e}"),
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn req(cmd: &str, timeout_s: u64) -> SessionExecRequest {
        SessionExecRequest {
            cmd: cmd.to_string(),
            timeout_s,
        }
    }

    #[test]
    fn rejects_empty_cmd() {
        assert!(validate_exec(&req("   ", 30)).is_err());
    }

    #[test]
    fn rejects_too_long_cmd() {
        assert!(validate_exec(&req(&"a".repeat(4097), 30)).is_err());
    }

    #[test]
    fn rejects_bad_timeout() {
        assert!(validate_exec(&req("echo hi", 0)).is_err());
        assert!(validate_exec(&req("echo hi", 121)).is_err());
    }

    #[test]
    fn accepts_valid_request() {
        assert!(validate_exec(&req("echo hi", 30)).is_ok());
    }

    #[tokio::test]
    async fn session_map_insert_lookup_remove() {
        let sessions: Sessions = Arc::new(Mutex::new(HashMap::new()));
        sessions.lock().await.insert(
            "abc".to_string(),
            SessionEntry {
                container: "sandbox-session-abc".to_string(),
                last_used: Instant::now(),
            },
        );
        assert_eq!(
            container_for(&sessions, "abc").await,
            Some("sandbox-session-abc".to_string())
        );
        assert_eq!(container_for(&sessions, "nope").await, None);
        sessions.lock().await.remove("abc");
        assert_eq!(container_for(&sessions, "abc").await, None);
    }

    #[test]
    fn expired_ids_only_returns_idle_sessions() {
        let mut entries: HashMap<String, SessionEntry> = HashMap::new();
        entries.insert(
            "stale".to_string(),
            SessionEntry {
                container: "sandbox-session-stale".to_string(),
                last_used: Instant::now() - Duration::from_secs(100),
            },
        );
        entries.insert(
            "fresh".to_string(),
            SessionEntry {
                container: "sandbox-session-fresh".to_string(),
                last_used: Instant::now(),
            },
        );
        let mut expired = expired_ids(&entries, Duration::from_secs(30));
        expired.sort();
        assert_eq!(expired, vec!["stale".to_string()]);
    }

    #[test]
    fn expired_ids_empty_for_empty_map() {
        assert!(expired_ids(&HashMap::new(), Duration::from_secs(30)).is_empty());
    }

    #[test]
    fn session_ids_are_unique() {
        let a = unique_session_id();
        let b = unique_session_id();
        assert_ne!(a, b);
    }
}
