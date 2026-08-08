use sandbox_gateway::app;

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let addr = "0.0.0.0:8080";
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    tracing::info!("sandbox-gateway listening on http://{addr}");
    axum::serve(listener, app()).await.unwrap();
}
