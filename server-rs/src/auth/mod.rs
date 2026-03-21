use std::sync::Arc;

use axum::{
    extract::{FromRef, FromRequestParts},
    http::{request::Parts, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use axum_extra::extract::CookieJar;
use chrono::{Duration, Utc};
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use serde_json::json;
use subtle::ConstantTimeEq;
use tokio::sync::Mutex;

use crate::config::{AppConfig, AuthType};
use crate::error::AppError;
use crate::models::{LoginRequest, TokenResponse};

#[derive(Debug, Serialize, Deserialize)]
struct Claims {
    sub: String,
    exp: usize,
}

#[derive(Clone)]
pub struct AuthState {
    config: Arc<AppConfig>,
    last_totp: Arc<Mutex<Option<String>>>,
}

impl AuthState {
    pub fn new(config: Arc<AppConfig>) -> Self {
        if config.auth_type == AuthType::Totp {
            if let Some(ref key) = config.totp_key {
                print_totp_qr(&config.username.as_deref().unwrap_or("memlog"), key);
            }
        }
        Self {
            config,
            last_totp: Arc::new(Mutex::new(None)),
        }
    }

    pub async fn login(&self, req: &LoginRequest) -> Result<TokenResponse, AppError> {
        let cfg = &self.config;
        let expected_user = cfg.username.as_deref().unwrap_or("");
        let expected_pass = cfg.password.as_deref().unwrap_or("");

        // Constant-time username check
        let user_ok = bool::from(
            req.username
                .as_bytes()
                .ct_eq(expected_user.to_lowercase().as_bytes()),
        ) || bool::from(
            req.username
                .to_lowercase()
                .as_bytes()
                .ct_eq(expected_user.to_lowercase().as_bytes()),
        );

        // Build expected password (append TOTP code if enabled)
        let full_expected_pass = if cfg.auth_type == AuthType::Totp {
            let totp_code = self.current_totp_code()?;
            format!("{expected_pass}{totp_code}")
        } else {
            expected_pass.to_string()
        };

        let pass_ok = bool::from(req.password.as_bytes().ct_eq(full_expected_pass.as_bytes()));

        if !user_ok || !pass_ok {
            return Err(AppError::Unauthorized);
        }

        // TOTP replay protection
        if cfg.auth_type == AuthType::Totp {
            let code = self.current_totp_code()?;
            let mut last = self.last_totp.lock().await;
            if last.as_deref() == Some(&code) {
                return Err(AppError::Unauthorized);
            }
            *last = Some(code);
        }

        let secret = cfg
            .secret_key
            .as_deref()
            .ok_or_else(|| AppError::Internal(anyhow::anyhow!("MEMLOG_SECRET_KEY not set")))?;

        let exp = (Utc::now() + Duration::days(cfg.session_expiry_days)).timestamp() as usize;
        let claims = Claims { sub: req.username.clone(), exp };
        let token = encode(
            &Header::default(),
            &claims,
            &EncodingKey::from_secret(secret.as_bytes()),
        )
        .map_err(|e| AppError::Internal(e.into()))?;

        Ok(TokenResponse { access_token: token, token_type: "bearer".to_string() })
    }

    pub fn validate_token(&self, token: &str) -> Result<(), AppError> {
        let secret = self
            .config
            .secret_key
            .as_deref()
            .ok_or_else(|| AppError::Internal(anyhow::anyhow!("MEMLOG_SECRET_KEY not set")))?;
        let expected_user = self.config.username.as_deref().unwrap_or("");

        let data = decode::<Claims>(
            token,
            &DecodingKey::from_secret(secret.as_bytes()),
            &Validation::default(),
        )
        .map_err(|_| AppError::Unauthorized)?;

        if data.claims.sub.to_lowercase() != expected_user.to_lowercase() {
            return Err(AppError::Unauthorized);
        }
        Ok(())
    }

    fn current_totp_code(&self) -> Result<String, AppError> {
        use totp_rs::{Algorithm, Secret, TOTP};
        let key = self
            .config
            .totp_key
            .as_deref()
            .ok_or_else(|| AppError::Internal(anyhow::anyhow!("MEMLOG_TOTP_KEY not set")))?;
        let secret_bytes = Secret::Encoded(key.to_string())
            .to_bytes()
            .map_err(|e| AppError::Internal(anyhow::anyhow!("Invalid TOTP key: {e}")))?;
        let totp = TOTP::new(Algorithm::SHA1, 6, 1, 30, secret_bytes, None, "memlog".to_string())
            .map_err(|e| AppError::Internal(anyhow::anyhow!("{e}")))?;
        totp.generate_current()
            .map_err(|e| AppError::Internal(anyhow::anyhow!("{e}")))
    }
}

fn print_totp_qr(username: &str, key: &str) {
    use qrcode::{render::unicode, QrCode};
    // Remove padding per Google Authenticator spec (same as Python impl)
    let key_no_pad = key.trim_end_matches('=');
    let uri = format!(
        "otpauth://totp/memlog:{username}?secret={key_no_pad}&issuer=memlog"
    );
    match QrCode::new(uri.as_bytes()) {
        Ok(code) => {
            let image = code.render::<unicode::Dense1x2>().build();
            println!("\nScan this QR code in your authenticator app:\n{image}");
            println!("Or enter the key manually: {key}\n");
        }
        Err(e) => tracing::warn!("Could not generate TOTP QR code: {e}"),
    }
}

// ── Axum extractor ────────────────────────────────────────────────────────

/// Marker type: request has valid auth (or auth is not required).
pub struct AuthenticatedUser;

impl<S> FromRequestParts<S> for AuthenticatedUser
where
    S: Send + Sync,
    Arc<AuthState>: FromRef<S>,
{
    type Rejection = AuthRejection;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        let auth_state = Arc::<AuthState>::from_ref(state);
        let cfg = &auth_state.config;

        // No auth needed for these modes
        if cfg.auth_type == AuthType::None || cfg.auth_type == AuthType::ReadOnly {
            return Ok(AuthenticatedUser);
        }

        // Try Authorization: Bearer header
        let token = if let Some(header) = parts.headers.get("authorization") {
            let val = header.to_str().unwrap_or("");
            if let Some(tok) = val.strip_prefix("Bearer ") {
                Some(tok.to_string())
            } else {
                None
            }
        } else {
            None
        };

        // Fall back to cookie
        let token = token.or_else(|| {
            let jar = CookieJar::from_headers(&parts.headers);
            jar.get("token").map(|c| c.value().to_string())
        });

        match token {
            Some(tok) => auth_state
                .validate_token(&tok)
                .map(|_| AuthenticatedUser)
                .map_err(|_| AuthRejection),
            None => Err(AuthRejection),
        }
    }
}

pub struct AuthRejection;

impl IntoResponse for AuthRejection {
    fn into_response(self) -> Response {
        (
            StatusCode::UNAUTHORIZED,
            Json(json!({"detail": "Invalid authentication credentials"})),
        )
            .into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::{AppConfig, AuthType};
    use std::path::PathBuf;

    fn password_auth() -> AuthState {
        AuthState::new(Arc::new(AppConfig {
            notes_path: PathBuf::from("/tmp"),
            auth_type: AuthType::Password,
            username: Some("testuser".to_string()),
            password: Some("testpass".to_string()),
            secret_key: Some("testsecret".to_string()),
            session_expiry_days: 30,
            totp_key: None,
            quick_access_hide: false,
            quick_access_title: "RECENTLY MODIFIED".to_string(),
            quick_access_term: "*".to_string(),
            quick_access_sort: "lastModified".to_string(),
            quick_access_limit: 4,
            path_prefix: String::new(),
        }))
    }

    #[tokio::test]
    async fn test_login_success() {
        let auth = password_auth();
        let req = LoginRequest {
            username: "testuser".to_string(),
            password: "testpass".to_string(),
        };
        let token = auth.login(&req).await.unwrap();
        assert!(!token.access_token.is_empty());
        assert_eq!(token.token_type, "bearer");
    }

    #[tokio::test]
    async fn test_login_wrong_password() {
        let auth = password_auth();
        let req = LoginRequest {
            username: "testuser".to_string(),
            password: "wrongpass".to_string(),
        };
        assert!(matches!(auth.login(&req).await, Err(AppError::Unauthorized)));
    }

    #[tokio::test]
    async fn test_login_wrong_username() {
        let auth = password_auth();
        let req = LoginRequest {
            username: "nobody".to_string(),
            password: "testpass".to_string(),
        };
        assert!(matches!(auth.login(&req).await, Err(AppError::Unauthorized)));
    }

    #[tokio::test]
    async fn test_login_username_case_insensitive() {
        let auth = password_auth();
        let req = LoginRequest {
            username: "TESTUSER".to_string(),
            password: "testpass".to_string(),
        };
        let token = auth.login(&req).await.unwrap();
        assert!(!token.access_token.is_empty());
    }

    #[tokio::test]
    async fn test_valid_token_validates() {
        let auth = password_auth();
        let req = LoginRequest {
            username: "testuser".to_string(),
            password: "testpass".to_string(),
        };
        let token = auth.login(&req).await.unwrap();
        assert!(auth.validate_token(&token.access_token).is_ok());
    }

    #[test]
    fn test_invalid_token_rejected() {
        let auth = password_auth();
        assert!(auth.validate_token("not.a.token").is_err());
    }

    #[test]
    fn test_empty_token_rejected() {
        let auth = password_auth();
        assert!(auth.validate_token("").is_err());
    }

    #[tokio::test]
    async fn test_wrong_secret_rejected() {
        let auth = password_auth();
        let req = LoginRequest {
            username: "testuser".to_string(),
            password: "testpass".to_string(),
        };
        let token = auth.login(&req).await.unwrap();

        // Validate with a different secret key
        let other_auth = AuthState::new(Arc::new(AppConfig {
            notes_path: PathBuf::from("/tmp"),
            auth_type: AuthType::Password,
            username: Some("testuser".to_string()),
            password: Some("testpass".to_string()),
            secret_key: Some("different_secret".to_string()),
            session_expiry_days: 30,
            totp_key: None,
            quick_access_hide: false,
            quick_access_title: "RECENTLY MODIFIED".to_string(),
            quick_access_term: "*".to_string(),
            quick_access_sort: "lastModified".to_string(),
            quick_access_limit: 4,
            path_prefix: String::new(),
        }));
        assert!(other_auth.validate_token(&token.access_token).is_err());
    }
}
