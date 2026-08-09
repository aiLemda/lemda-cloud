use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use tower::ServiceExt;

use sandbox_gateway::app;

#[tokio::test]
async fn exec_rejects_empty_cmd() {
    let response = app()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/exec")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"cmd":""}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
    let body = response.into_body().collect().await.unwrap().to_bytes();
    assert!(String::from_utf8_lossy(&body).contains("cmd must not be empty"));
}

#[tokio::test]
async fn exec_rejects_bad_timeout() {
    let response = app()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/exec")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"cmd":"echo hi","timeout_s":999}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
}
