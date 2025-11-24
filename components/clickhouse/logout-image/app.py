import os
import urllib.parse
from flask import Flask, request, redirect, make_response, Response

app = Flask(__name__)

# --------------------------
# Env config
# --------------------------
COGNITO_CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]
COGNITO_DOMAIN = os.environ["COGNITO_DOMAIN"]

# Optional global default redirect (used only if nothing else is available)
GLOBAL_LOGOUT_REDIRECT = (
    os.environ.get("LOGOUT_REDIRECT")
    or os.environ.get("LOGOUT_REDIRECT_URI")
    or None
)

# Must match the ALB cookie domain (e.g. ".usekarma.dev")
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN")

# Prefix for ALB auth cookies (e.g. alb_auth-0, alb_auth-1)
ALB_COOKIE_PREFIX = os.environ.get("ALB_COOKIE_PREFIX", "alb_auth")

# Debug: set DEBUG_LOGOUT=true to always dump, or use ?debug=1
DEBUG_LOGOUT = os.environ.get("DEBUG_LOGOUT", "false").lower() in ("1", "true", "yes")


def _infer_scheme() -> str:
    """
    Try to reconstruct the external scheme (http/https) as seen by the client.
    Behind ALB this will usually be 'https' via X-Forwarded-Proto.
    """
    xf_proto = request.headers.get("X-Forwarded-Proto")
    if xf_proto:
        # Avoid weird/multi values; just take the first if comma-separated
        return xf_proto.split(",")[0].strip()
    return request.scheme or "https"


def _compute_logout_redirect() -> str:
    """
    Compute where Cognito should send the user after logout.

    Priority:
      1) Explicit ?redirect_uri=<url> query param
      2) GLOBAL_LOGOUT_REDIRECT env (LOGOUT_REDIRECT / LOGOUT_REDIRECT_URI)
      3) Same host the request came from, root path (e.g. https://clickhouse.usekarma.dev/)
    """
    # 1) Per-call override
    redirect_uri_param = request.args.get("redirect_uri")
    if redirect_uri_param:
        return redirect_uri_param

    # 2) Global env-based default
    if GLOBAL_LOGOUT_REDIRECT:
        return GLOBAL_LOGOUT_REDIRECT

    # 3) Fallback: same host, root path
    scheme = _infer_scheme()
    host = request.host or "grafana.usekarma.dev"
    return f"{scheme}://{host}/"


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/logout")
def logout():
    """
    1. Log what we see (host, path, cookies, env bits).
    2. Expire ALB auth cookies (alb_auth-*) and optionally Grafana cookies.
    3. Redirect to Cognito Hosted UI /logout endpoint with client_id + logout_uri,
       OR, in debug mode, return a text dump instead of redirecting.
    """
    debug = DEBUG_LOGOUT or (request.args.get("debug") == "1")

    logout_redirect = _compute_logout_redirect()

    info = []
    info.append("=== /logout debug ===")
    info.append(f"debug_mode = {debug}")
    info.append(f"request.url = {request.url}")
    info.append(f"request.host = {request.host}")
    info.append(f"request.remote_addr = {request.remote_addr}")
    info.append(f"X-Forwarded-Proto = {request.headers.get('X-Forwarded-Proto')}")
    info.append(f"COGNITO_CLIENT_ID = {COGNITO_CLIENT_ID}")
    info.append(f"COGNITO_DOMAIN    = {COGNITO_DOMAIN}")
    info.append(f"GLOBAL_LOGOUT_REDIRECT = {GLOBAL_LOGOUT_REDIRECT}")
    info.append(f"computed_logout_redirect = {logout_redirect}")
    info.append(f"COOKIE_DOMAIN     = {COOKIE_DOMAIN}")
    info.append(f"ALB_COOKIE_PREFIX = {ALB_COOKIE_PREFIX}")

    cookie_names = list(request.cookies.keys())
    info.append(f"cookies_seen = {cookie_names}")

    # Match your ALB cookies: alb_auth-0, alb_auth-1, etc.
    alb_cookies = [c for c in cookie_names if c.startswith(ALB_COOKIE_PREFIX)]
    info.append(f"alb_cookies = {alb_cookies}")

    # Also consider nuking Grafana session cookies
    grafana_cookies = [c for c in cookie_names if c.startswith("grafana_")]
    info.append(f"grafana_cookies = {grafana_cookies}")

    # Build Cognito logout URL
    cognito_logout = (
        f"https://{COGNITO_DOMAIN}/logout"
        f"?client_id={urllib.parse.quote(COGNITO_CLIENT_ID)}"
        f"&logout_uri={urllib.parse.quote(logout_redirect, safe='')}"
    )
    info.append(f"cognito_logout_url = {cognito_logout}")

    # Response: redirect normally, text in debug
    if debug:
        resp = make_response("DEBUG\n", 200)
    else:
        resp = make_response(redirect(cognito_logout))

    delete_ops = []

    # ---- Delete ALB auth cookies (critical) ----
    for cookie_name in alb_cookies:
        # Domain cookie (e.g. .usekarma.dev)
        if COOKIE_DOMAIN:
            delete_ops.append(
                f"delete_cookie(name={cookie_name}, domain={COOKIE_DOMAIN}, path=/)"
            )
            resp.delete_cookie(
                cookie_name,
                path="/",
                domain=COOKIE_DOMAIN,
            )

        # Host-only cookie
        delete_ops.append(
            f"delete_cookie(name={cookie_name}, domain=None, path=/)"
        )
        resp.delete_cookie(
            cookie_name,
            path="/",
        )

    # ---- Optionally delete Grafana session cookies ----
    for cookie_name in grafana_cookies:
        if COOKIE_DOMAIN:
            delete_ops.append(
                f"delete_cookie(name={cookie_name}, domain={COOKIE_DOMAIN}, path=/)"
            )
            resp.delete_cookie(
                cookie_name,
                path="/",
                domain=COOKIE_DOMAIN,
            )

        delete_ops.append(
            f"delete_cookie(name={cookie_name}, domain=None, path=/)"
        )
        resp.delete_cookie(
            cookie_name,
            path="/",
        )

    info.append(f"delete_ops = {delete_ops}")

    # Log to CloudWatch
    for line in info:
        app.logger.info(line)

    if debug:
        body = "\n".join(info) + "\n"
        return Response(body, mimetype="text/plain", status=200)

    return resp


if __name__ == "__main__":
    # For local testing only; in ECS we run via gunicorn
    app.run(host="0.0.0.0", port=8080)
