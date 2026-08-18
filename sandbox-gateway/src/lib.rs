mod exec;
mod sessions;

use std::collections::HashMap;
use std::sync::Arc;

use axum::extract::Json;
use axum::http::StatusCode;
use axum::routing::{delete, get, post};
use axum::Router;

use crate::exec::{ExecRequest, ExecResult};

pub fn app() -> Router {
    let sessions: sessions::Sessions = Arc::new(tokio::sync::Mutex::new(HashMap::new()));
    sessions::start_reaper(sessions.clone());
    Router::new()
        .route("/healthz", get(healthz))
        .route("/exec", post(exec_handler))
        .route("/sessions", post(sessions::create_session_handler))
        .route(
            "/sessions/{session_id}/exec",
            post(sessions::exec_in_session_handler),
        )
        .route("/sessions/{session_id}", delete(sessions::delete_session_handler))
        .with_state(sessions)
}

async fn healthz() -> &'static str {
    "ok"
}

async fn exec_handler(Json(req): Json<ExecRequest>) -> Result<Json<ExecResult>, (StatusCode, String)> {
    if let Err(e) = exec::validate(&req) {
        return Err((StatusCode::UNPROCESSABLE_ENTITY, e));
    }
    Ok(Json(exec::run_exec(&req).await))
}
