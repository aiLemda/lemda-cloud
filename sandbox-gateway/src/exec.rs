use std::process::Stdio;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use tokio::process::Command;
use tokio::time::timeout;

const MAX_CMD_LEN: usize = 4096;
const DEFAULT_IMAGE: &str = "python:3.12-slim";
const EGRESS_PROXY: &str = "http://sandbox-egress:8888";
const SANDBOX_NET: &str = "sandbox-net";
const NO_PROXY: &str = "localhost,127.0.0.1";

#[derive(Debug, Deserialize)]
pub struct ExecRequest {
    pub cmd: String,
    #[serde(default = "default_image")]
    pub image: String,
    #[serde(default = "default_timeout")]
    pub timeout_s: u64,
}

fn default_image() -> String {
    DEFAULT_IMAGE.to_string()
}

fn default_timeout() -> u64 {
    30
}

#[derive(Debug, Serialize)]
pub struct ExecResult {
    pub exit_code: Option<i32>,
    pub stdout: String,
    pub stderr: String,
    pub timed_out: bool,
    pub duration_ms: u64,
}

pub fn validate(req: &ExecRequest) -> Result<(), String> {
    if req.cmd.trim().is_empty() {
        return Err("cmd must not be empty".to_string());
    }
    if req.cmd.len() > MAX_CMD_LEN {
        return Err(format!("cmd too long (max {MAX_CMD_LEN} chars)"));
    }
    if !(1..=120).contains(&req.timeout_s) {
        return Err("timeout_s must be between 1 and 120".to_string());
    }
    Ok(())
}

pub async fn run_exec(req: &ExecRequest) -> ExecResult {
    let started = Instant::now();
    let name = unique_name();

    let child = match spawn_sandbox(&name, req) {
        Ok(c) => c,
        Err(e) => {
            return ExecResult {
                exit_code: None,
                stdout: String::new(),
                stderr: format!("failed to start sandbox container: {e}"),
                timed_out: false,
                duration_ms: started.elapsed().as_millis() as u64,
            }
        }
    };

    let waited = timeout(Duration::from_secs(req.timeout_s), child.wait_with_output()).await;

    match waited {
        Ok(Ok(output)) => ExecResult {
            exit_code: output.status.code(),
            stdout: String::from_utf8_lossy(&output.stdout).to_string(),
            stderr: String::from_utf8_lossy(&output.stderr).to_string(),
            timed_out: false,
            duration_ms: started.elapsed().as_millis() as u64,
        },
        Ok(Err(e)) => ExecResult {
            exit_code: None,
            stdout: String::new(),
            stderr: format!("failed to run command: {e}"),
            timed_out: false,
            duration_ms: started.elapsed().as_millis() as u64,
        },
        Err(_) => {
            let _ = Command::new("docker")
                .args(["kill", &name])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
                .await;
            ExecResult {
                exit_code: None,
                stdout: String::new(),
                stderr: "command timed out - sandbox container killed".to_string(),
                timed_out: true,
                duration_ms: started.elapsed().as_millis() as u64,
            }
        }
    }
}

fn unique_name() -> String {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    format!("sandbox-exec-{millis}")
}

fn spawn_sandbox(name: &str, req: &ExecRequest) -> Result<tokio::process::Child, std::io::Error> {
    let mut args: Vec<String> = vec![
        "run".into(),
        "--rm".into(),
        "--name".into(),
        name.into(),
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
    args.push(req.image.clone());
    args.push("sh".into());
    args.push("-lc".into());
    args.push(req.cmd.clone());

    Command::new("docker")
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn req(cmd: &str, timeout_s: u64) -> ExecRequest {
        ExecRequest {
            cmd: cmd.to_string(),
            image: default_image(),
            timeout_s,
        }
    }

    #[test]
    fn rejects_empty_cmd() {
        assert!(validate(&req("   ", 30)).is_err());
    }

    #[test]
    fn rejects_too_long_cmd() {
        assert!(validate(&req(&"a".repeat(MAX_CMD_LEN + 1), 30)).is_err());
    }

    #[test]
    fn rejects_bad_timeout() {
        assert!(validate(&req("echo hi", 0)).is_err());
        assert!(validate(&req("echo hi", 121)).is_err());
    }

    #[test]
    fn accepts_valid_request() {
        assert!(validate(&req("echo hi", 30)).is_ok());
    }
}
