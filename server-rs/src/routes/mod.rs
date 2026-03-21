use axum::{
    extract::{Multipart, Path, Query, State},
    http::StatusCode,
    response::{Html, IntoResponse, Response},
    routing::{delete, get, patch, post},
    Json, Router,
};
use serde::Deserialize;
use tower_http::services::ServeDir;

use crate::{
    auth::AuthenticatedUser,
    error::AppError,
    models::*,
    AppState,
};

// ── Route builder ────────────────────────────────────────────────────────────

pub fn build_router(state: AppState) -> Router {
    let cfg = state.config.clone();
    let prefix = cfg.path_prefix.clone();

    let mut api = Router::new()
        .route("/auth-check", get(auth_check))
        .route("/notes/{title}", get(get_note))
        .route("/search", get(search))
        .route("/tags", get(get_tags))
        .route("/attachments/{filename}", get(get_attachment))
        .route("/config", get(get_config))
        .route("/version", get(get_version))
        .route("/health", get(healthcheck)); // also exposed at root

    // Write routes — disabled in read_only mode
    if !cfg.auth_type.is_read_only() {
        api = api
            .route("/notes", post(create_note))
            .route("/notes/{title}", patch(update_note))
            .route("/notes/{title}", delete(delete_note))
            .route("/attachments", post(upload_attachment));
    }

    // Token endpoint — only when auth requires it
    if cfg.auth_type.requires_write_auth() {
        api = api.route("/token", post(login));
    }

    // SPA shell routes
    let spa_routes = Router::new()
        .route("/", get(spa_shell))
        .route("/login", get(spa_shell))
        .route("/search", get(spa_shell))
        .route("/new", get(spa_shell))
        .route("/note/{*title}", get(spa_shell));

    let mut root = Router::new()
        .route("/health", get(healthcheck))
        .nest("/api", api)
        .merge(spa_routes);

    // Static files from client/dist/
    let dist_path = std::path::PathBuf::from("client/dist");
    if dist_path.exists() {
        root = root.fallback_service(ServeDir::new(&dist_path));
    }

    // Attachment alias: GET /attachments/{filename} (non-API path for relative links in notes)
    root = root.route(
        "/attachments/{filename}",
        get({
            let st = state.clone();
            move |path: Path<String>| {
                let st = st.clone();
                async move { serve_attachment(State(st), path).await }
            }
        }),
    );

    if prefix.is_empty() {
        root.with_state(state)
    } else {
        Router::new()
            .nest(&prefix, root)
            .with_state(state)
    }
}

// ── Handlers ─────────────────────────────────────────────────────────────────

async fn healthcheck() -> &'static str {
    "OK"
}

async fn spa_shell() -> Response {
    let index_path = std::path::Path::new("client/dist/index.html");
    match tokio::fs::read_to_string(index_path).await {
        Ok(html) => Html(html).into_response(),
        Err(_) => (StatusCode::NOT_FOUND, "index.html not found").into_response(),
    }
}

async fn get_version() -> Json<serde_json::Value> {
    Json(serde_json::json!({"version": env!("CARGO_PKG_VERSION")}))
}

async fn get_config(State(state): State<AppState>) -> Json<ConfigResponse> {
    let cfg = &state.config;
    Json(ConfigResponse {
        auth_type: format!("{:?}", cfg.auth_type).to_lowercase(),
        quick_access_hide: cfg.quick_access_hide,
        quick_access_title: cfg.quick_access_title.clone(),
        quick_access_term: cfg.quick_access_term.clone(),
        quick_access_sort: cfg.quick_access_sort.clone(),
        quick_access_limit: cfg.quick_access_limit,
    })
}

async fn auth_check(
    _auth: AuthenticatedUser,
) -> &'static str {
    "OK"
}

async fn login(
    State(state): State<AppState>,
    Json(req): Json<LoginRequest>,
) -> Result<Json<TokenResponse>, AppError> {
    let token = state.auth.login(&req).await?;
    Ok(Json(token))
}

// ── Notes ─────────────────────────────────────────────────────────────────────

async fn get_note(
    _auth: AuthenticatedUser,
    State(state): State<AppState>,
    Path(title): Path<String>,
) -> Result<Json<Note>, AppError> {
    let note = state.notes.get(&title).await?;
    Ok(Json(note))
}

async fn create_note(
    _auth: AuthenticatedUser,
    State(state): State<AppState>,
    Json(data): Json<NoteCreate>,
) -> Result<(StatusCode, Json<Note>), AppError> {
    let note = state.notes.create(data).await?;
    Ok((StatusCode::CREATED, Json(note)))
}

async fn update_note(
    _auth: AuthenticatedUser,
    State(state): State<AppState>,
    Path(title): Path<String>,
    Json(data): Json<NoteUpdate>,
) -> Result<Json<Note>, AppError> {
    let note = state.notes.update(&title, data).await?;
    Ok(Json(note))
}

async fn delete_note(
    _auth: AuthenticatedUser,
    State(state): State<AppState>,
    Path(title): Path<String>,
) -> Result<StatusCode, AppError> {
    state.notes.delete(&title).await?;
    Ok(StatusCode::NO_CONTENT)
}

// ── Search ─────────────────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct SearchParams {
    term: String,
    sort: Option<String>,
    order: Option<String>,
    limit: Option<usize>,
}

async fn search(
    _auth: AuthenticatedUser,
    State(state): State<AppState>,
    Query(params): Query<SearchParams>,
) -> Result<Json<Vec<SearchResult>>, AppError> {
    let sort = params.sort.as_deref().unwrap_or("score");
    let order = params.order.as_deref().unwrap_or("desc");
    let results = tokio::task::spawn_blocking({
        let index = state.search.clone();
        let term = params.term.clone();
        let sort = sort.to_string();
        let order = order.to_string();
        let limit = params.limit;
        move || index.search(&term, &sort, &order, limit)
    })
    .await
    .map_err(|e| AppError::Internal(anyhow::anyhow!(e)))??;
    Ok(Json(results))
}

async fn get_tags(
    _auth: AuthenticatedUser,
    State(state): State<AppState>,
) -> Result<Json<Vec<String>>, AppError> {
    let tags = tokio::task::spawn_blocking({
        let index = state.search.clone();
        move || index.get_tags()
    })
    .await
    .map_err(|e| AppError::Internal(anyhow::anyhow!(e)))??;
    Ok(Json(tags))
}

// ── Attachments ───────────────────────────────────────────────────────────────

async fn get_attachment(
    _auth: AuthenticatedUser,
    State(state): State<AppState>,
    Path(filename): Path<String>,
) -> Result<Response, AppError> {
    serve_attachment(State(state), Path(filename)).await
}

async fn serve_attachment(
    State(state): State<AppState>,
    Path(filename): Path<String>,
) -> Result<Response, AppError> {
    let path = state.attachments.path_for(&filename)?;
    let mime = mime_guess::from_path(&filename)
        .first_or_octet_stream()
        .to_string();
    let data = tokio::fs::read(&path)
        .await
        .map_err(|_| AppError::AttachmentNotFound)?;
    Ok((
        [(axum::http::header::CONTENT_TYPE, mime)],
        data,
    )
        .into_response())
}

async fn upload_attachment(
    _auth: AuthenticatedUser,
    State(state): State<AppState>,
    multipart: Multipart,
) -> Result<(StatusCode, Json<AttachmentCreateResponse>), AppError> {
    let resp = state.attachments.create(multipart).await?;
    Ok((StatusCode::CREATED, Json(resp)))
}
