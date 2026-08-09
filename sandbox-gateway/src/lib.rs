mod exec;

use axum::extract::Json;
use axum::http::StatusCode;
use axum::routing::{get, post};
use axum::Router;

use crate::exec::{ExecRequest, ExecResult};

pub fn app() -> Router {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/exec", post(exec_handler))
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
