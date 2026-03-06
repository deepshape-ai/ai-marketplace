#!/usr/bin/env python3
"""
usememos CLI - Secure wrapper for usememos API calls.

This script provides a secure interface to interact with usememos API
without exposing API tokens in command-line arguments or logs.

Configuration:
  - USEMEMOS_API_TOKEN: API token (required)
  - USEMEMOS_SITE_URL: Site URL (required)
  - USEMEMOS_CONFIG_FILE: Config file path (default: ~/.usememos/config.json)

Usage:
  python usememos_cli.py <command> [options]

Commands:
  auth              Authentication operations
  memo              Memo operations (read and write)
  user              User operations (read-only)
  activity          Activity operations (read-only)
  attachment        Attachment operations (read-only)
  shortcut          Shortcut operations (read-only)
  identity-provider Identity provider operations (read-only)
  instance          Instance operations (read-only)
"""

import argparse
import base64
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import numpy as np
except ImportError:  # pragma: no cover - handled at runtime
    np = None


class UseMemosError(Exception):
    """Base exception for usememos CLI errors."""


class ConfigurationError(UseMemosError):
    """Configuration related errors."""


class APIError(UseMemosError):
    """API related errors."""

    def __init__(self, status_code: int, message: str, details: Optional[Dict[str, Any]] = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(f"API Error {status_code}: {message}")


class CLIArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that raises validation errors instead of writing raw stderr usage."""

    def error(self, message: str) -> None:
        raise UseMemosError(f"Argument error: {message}")


def parse_user_id_from_jwt(token: str) -> Optional[str]:
    """Extract user id from JWT `sub` claim without signature verification."""
    if token.count(".") != 2:
        return None

    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)
        user_id = payload.get("sub")
        if isinstance(user_id, str) and user_id:
            return user_id
    except Exception:
        return None

    return None


def normalize_resource_id(resource: str, prefix: str) -> str:
    """Normalize id input by accepting either `id` or `prefix/id` forms."""
    value = (resource or "").strip()
    if not value:
        raise UseMemosError("Resource id cannot be empty")

    prefix_with_slash = f"{prefix}/"
    if value.startswith(prefix_with_slash):
        return value[len(prefix_with_slash) :]

    return value


def normalize_user_id(user_id: str) -> str:
    return normalize_resource_id(user_id, "users")


def normalize_memo_id(memo_id: str) -> str:
    return normalize_resource_id(memo_id, "memos")


def normalize_attachment_id(attachment_id: str) -> str:
    return normalize_resource_id(attachment_id, "attachments")


def normalize_activity_id(activity_id: str) -> str:
    return normalize_resource_id(activity_id, "activities")


def normalize_shortcut_id(shortcut_id: str) -> str:
    return normalize_resource_id(shortcut_id, "shortcuts")


def normalize_identity_provider_id(provider_id: str) -> str:
    return normalize_resource_id(provider_id, "identity-providers")


def build_update_mask(payload: Dict[str, Any]) -> str:
    """Build field mask from non-empty payload fields."""
    fields = [k for k, v in payload.items() if v is not None]
    if not fields:
        raise UseMemosError("No fields to update. Provide at least one updatable field.")
    return ",".join(fields)


def compact_memo(memo: Dict[str, Any]) -> Dict[str, Any]:
    """Return token-efficient memo representation."""
    return {
        "name": memo.get("name"),
        "creator": memo.get("creator"),
        "displayTime": memo.get("displayTime"),
        "updateTime": memo.get("updateTime"),
        "visibility": memo.get("visibility"),
        "pinned": memo.get("pinned"),
        "tags": memo.get("tags", []),
        "snippet": memo.get("snippet") or (memo.get("content", "")[:240] + "..." if memo.get("content") else ""),
    }


def tokenize_text(text: str) -> List[str]:
    """Generic tokenizer for multilingual text."""
    if not text:
        return []

    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9]+", lowered)

    # Add CJK bi-grams to improve semantic recall without hardcoded dictionaries.
    for chunk in re.findall(r"[\u4e00-\u9fff]+", lowered):
        if len(chunk) == 1:
            tokens.append(chunk)
            continue
        tokens.extend(chunk[i : i + 2] for i in range(len(chunk) - 1))

    return tokens


def memo_text_for_ranking(memo: Dict[str, Any]) -> str:
    parts = [
        memo.get("content") or "",
        memo.get("snippet") or "",
        " ".join(memo.get("tags") or []),
    ]
    return "\n".join([p for p in parts if p])


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


def build_tfidf_space(
    doc_tokens: List[List[str]],
    query_tokens: List[str],
    max_terms: int = 5000,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, int]]:
    if np is None:
        raise UseMemosError("Semantic search requires numpy. Please install numpy first.")

    doc_count = len(doc_tokens)
    if doc_count == 0:
        return np.zeros((0, 0)), np.zeros((0,)), {}

    df: Dict[str, int] = defaultdict(int)
    tf_total: Dict[str, int] = defaultdict(int)

    for tokens in doc_tokens:
        counts = Counter(tokens)
        for term, cnt in counts.items():
            tf_total[term] += cnt
        for term in counts.keys():
            df[term] += 1

    query_unique = []
    seen_query = set()
    for token in query_tokens:
        if token not in seen_query:
            seen_query.add(token)
            query_unique.append(token)

    sorted_terms = sorted(
        df.keys(),
        key=lambda term: (df[term], tf_total[term], term),
        reverse=True,
    )

    vocab_terms = []
    for token in query_unique:
        if token in df:
            vocab_terms.append(token)
    for term in sorted_terms:
        if term not in vocab_terms:
            vocab_terms.append(term)
        if len(vocab_terms) >= max_terms:
            break

    vocab = {term: idx for idx, term in enumerate(vocab_terms)}
    term_count = len(vocab)

    matrix = np.zeros((doc_count, term_count), dtype=float)
    idf = np.zeros((term_count,), dtype=float)
    for term, idx in vocab.items():
        idf[idx] = math.log((doc_count + 1) / (df.get(term, 0) + 1)) + 1.0

    for row_idx, tokens in enumerate(doc_tokens):
        counts = Counter(tokens)
        for term, cnt in counts.items():
            col_idx = vocab.get(term)
            if col_idx is None:
                continue
            tf_weight = 1.0 + math.log(cnt)
            matrix[row_idx, col_idx] = tf_weight * idf[col_idx]

    query_vector = np.zeros((term_count,), dtype=float)
    query_counts = Counter(query_tokens)
    for term, cnt in query_counts.items():
        col_idx = vocab.get(term)
        if col_idx is None:
            continue
        tf_weight = 1.0 + math.log(cnt)
        query_vector[col_idx] = tf_weight * idf[col_idx]

    return matrix, query_vector, vocab


def build_readable_excerpt(content: str, query_tokens: List[str], max_chars: int = 420) -> str:
    if not content:
        return ""

    content_lower = content.lower()
    positions = []
    for token in query_tokens:
        if len(token) < 2:
            continue
        pos = content_lower.find(token)
        if pos >= 0:
            positions.append(pos)

    if positions:
        center = min(positions)
        start = max(0, center - 120)
    else:
        start = 0

    end = min(len(content), start + max_chars)
    excerpt = content[start:end].strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(content) else ""
    return f"{prefix}{excerpt}{suffix}"


def memo_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return fallback


def rank_memos_semantic(
    query: str,
    memos: List[Dict[str, Any]],
    top_k: int = 8,
    min_score: float = 0.15,
    latent_dims: int = 24,
) -> List[Dict[str, Any]]:
    if np is None:
        raise UseMemosError("Semantic search requires numpy. Please install numpy first.")

    query_tokens = tokenize_text(query)
    if not query_tokens or not memos:
        return []

    doc_texts = [memo_text_for_ranking(memo) for memo in memos]
    doc_tokens = [tokenize_text(text) for text in doc_texts]
    matrix, query_vector, _ = build_tfidf_space(doc_tokens, query_tokens)

    if matrix.size == 0:
        return []

    lexical_scores = [cosine_similarity(query_vector, matrix[idx]) for idx in range(matrix.shape[0])]
    semantic_scores = list(lexical_scores)

    n_docs, n_terms = matrix.shape
    max_k = min(latent_dims, n_docs - 1, n_terms - 1)
    if max_k >= 1:
        try:
            _, singular_values, vt = np.linalg.svd(matrix, full_matrices=False)
            k = min(max_k, len(singular_values))
            basis = vt[:k].T  # [terms, k]
            doc_latent = matrix @ basis
            query_latent = query_vector @ basis
            semantic_scores = [cosine_similarity(query_latent, doc_latent[idx]) for idx in range(doc_latent.shape[0])]
        except np.linalg.LinAlgError:
            semantic_scores = list(lexical_scores)

    query_term_set = set(query_tokens)
    ranked: List[Dict[str, Any]] = []

    for idx, memo in enumerate(memos):
        doc_term_set = set(doc_tokens[idx])
        coverage = len(query_term_set.intersection(doc_term_set)) / max(len(query_term_set), 1)
        pinned_boost = 0.02 if memo.get("pinned") else 0.0
        score = (semantic_scores[idx] * 0.70) + (lexical_scores[idx] * 0.25) + (coverage * 0.05) + pinned_boost

        if score < min_score:
            continue

        content = memo.get("content") or ""
        ranked.append(
            {
                "name": memo.get("name"),
                "creator": memo.get("creator"),
                "displayTime": memo.get("displayTime"),
                "updateTime": memo.get("updateTime"),
                "visibility": memo.get("visibility"),
                "tags": memo.get("tags", []),
                "pinned": memo.get("pinned", False),
                "title": memo_title(content, memo.get("name", "memo")),
                "excerpt": build_readable_excerpt(content, query_tokens),
                "relevance": {
                    "score": round(score, 4),
                    "semantic": round(semantic_scores[idx], 4),
                    "lexical": round(lexical_scores[idx], 4),
                    "coverage": round(coverage, 4),
                },
            }
        )

    ranked.sort(key=lambda item: item["relevance"]["score"], reverse=True)
    return ranked[:top_k]


class UseMemosClient:
    """Secure client for usememos API operations."""

    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.base_url = self.config["site_url"].rstrip("/")
        self.api_token = self.config["api_token"]
        self._resolved_user: Optional[Dict[str, Any]] = None

    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, str]:
        api_token = os.environ.get("USEMEMOS_API_TOKEN")
        site_url = os.environ.get("USEMEMOS_SITE_URL")

        if api_token and site_url:
            return {"api_token": api_token, "site_url": site_url}

        config_file = config_path or os.environ.get("USEMEMOS_CONFIG_FILE", os.path.expanduser("~/.usememos/config.json"))
        if not os.path.exists(config_file):
            raise ConfigurationError(
                f"Configuration not found. Set USEMEMOS_API_TOKEN and USEMEMOS_SITE_URL "
                f"environment variables, or create config file at {config_file}"
            )

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in config file: {e}") from e

        if "api_token" not in config or "site_url" not in config:
            raise ConfigurationError("Config file must contain 'api_token' and 'site_url' fields")

        return config

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"

        if params:
            filtered_params = {k: v for k, v in params.items() if v is not None}
            if filtered_params:
                url = f"{url}?{urlencode(filtered_params)}"

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = None
        if data is not None:
            payload = json.dumps(data).encode("utf-8")

        try:
            request = Request(url, headers=headers, method=method, data=payload)
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                if not body:
                    return {}
                return json.loads(body)
        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            try:
                error_data = json.loads(error_body)
                raise APIError(e.code, error_data.get("message", str(e)), error_data) from e
            except json.JSONDecodeError:
                raise APIError(e.code, str(e), {"body": error_body}) from e
        except URLError as e:
            raise APIError(0, f"Network error: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise APIError(0, f"Invalid JSON response: {e}") from e

    def get_current_user(self) -> Dict[str, Any]:
        return self._make_request("GET", "/api/v1/auth/me")

    def resolve_current_user(self) -> Dict[str, Any]:
        """
        Resolve current user with resilient fallbacks.
        - Preferred: /api/v1/auth/me
        - Fallback: decode JWT sub and call /api/v1/users/{sub}
        """
        if self._resolved_user is not None:
            return self._resolved_user

        try:
            result = self.get_current_user()
            user = result.get("user")
            if isinstance(user, dict) and user.get("name"):
                self._resolved_user = user
                return user
        except APIError:
            # Some instances may not expose auth/me for PAT.
            pass

        jwt_user_id = parse_user_id_from_jwt(self.api_token)
        if jwt_user_id:
            user = self.get_user(jwt_user_id)
            if user.get("name"):
                self._resolved_user = user
                return user

        raise UseMemosError("Cannot resolve current user. Check token validity and instance compatibility.")

    def require_owner_memo(self, memo_id: str) -> Dict[str, Any]:
        memo = self.get_memo(memo_id)
        current_user = self.resolve_current_user()
        if memo.get("creator") != current_user.get("name"):
            raise UseMemosError(
                f"Permission denied: memo owner is {memo.get('creator')}, token user is {current_user.get('name')}. "
                "Write operations are allowed only on current user's memos."
            )
        return memo

    # Memo endpoints
    def list_memos(
        self,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
        state: Optional[str] = None,
        order_by: Optional[str] = None,
        filter_expr: Optional[str] = None,
        show_deleted: Optional[bool] = None,
    ) -> Dict[str, Any]:
        params = {
            "pageSize": page_size,
            "pageToken": page_token,
            "state": state,
            "orderBy": order_by,
            "filter": filter_expr,
            "showDeleted": show_deleted,
        }
        return self._make_request("GET", "/api/v1/memos", params=params)

    def get_memo(self, memo_id: str) -> Dict[str, Any]:
        memo = normalize_memo_id(memo_id)
        return self._make_request("GET", f"/api/v1/memos/{memo}")

    def create_memo(
        self,
        content: str,
        visibility: str = "PRIVATE",
        state: str = "NORMAL",
        pinned: bool = False,
        memo_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {"memoId": memo_id}
        payload = {
            "content": content,
            "visibility": visibility,
            "state": state,
            "pinned": pinned,
        }
        return self._make_request("POST", "/api/v1/memos", params=params, data=payload)

    def update_memo(
        self,
        memo_id: str,
        content: Optional[str] = None,
        visibility: Optional[str] = None,
        state: Optional[str] = None,
        pinned: Optional[bool] = None,
    ) -> Dict[str, Any]:
        memo = normalize_memo_id(memo_id)
        payload: Dict[str, Any] = {
            "name": f"memos/{memo}",
            "content": content,
            "visibility": visibility,
            "state": state,
            "pinned": pinned,
        }
        update_payload = {k: v for k, v in payload.items() if v is not None}
        if "name" not in update_payload:
            update_payload["name"] = f"memos/{memo}"

        mask_source = {k: v for k, v in update_payload.items() if k != "name"}
        update_mask = build_update_mask(mask_source)

        return self._make_request(
            "PATCH",
            f"/api/v1/memos/{memo}",
            params={"updateMask": update_mask},
            data=update_payload,
        )

    def list_memo_attachments(
        self,
        memo_id: str,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        memo = normalize_memo_id(memo_id)
        params = {"pageSize": page_size, "pageToken": page_token}
        return self._make_request("GET", f"/api/v1/memos/{memo}/attachments", params=params)

    def list_memo_comments(
        self,
        memo_id: str,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
        order_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        memo = normalize_memo_id(memo_id)
        params = {"pageSize": page_size, "pageToken": page_token, "orderBy": order_by}
        return self._make_request("GET", f"/api/v1/memos/{memo}/comments", params=params)

    def list_memo_relations(
        self,
        memo_id: str,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        memo = normalize_memo_id(memo_id)
        params = {"pageSize": page_size, "pageToken": page_token}
        return self._make_request("GET", f"/api/v1/memos/{memo}/relations", params=params)

    def list_memo_reactions(
        self,
        memo_id: str,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        memo = normalize_memo_id(memo_id)
        params = {"pageSize": page_size, "pageToken": page_token}
        return self._make_request("GET", f"/api/v1/memos/{memo}/reactions", params=params)

    def search_memos(
        self,
        query: str,
        page_size: int = 20,
        max_pages: int = 2,
        top_k: int = 8,
        min_score: float = 0.15,
        filter_expr: Optional[str] = None,
        order_by: Optional[str] = "pinned desc, display_time desc",
    ) -> Dict[str, Any]:
        """General semantic search with TF-IDF + LSA similarity."""
        memos: List[Dict[str, Any]] = []
        page_token = None

        for _ in range(max_pages):
            response = self.list_memos(
                page_size=page_size,
                page_token=page_token,
                filter_expr=filter_expr,
                order_by=order_by,
            )
            page_memos = response.get("memos", [])
            memos.extend(page_memos)
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        results = rank_memos_semantic(
            query=query,
            memos=memos,
            top_k=top_k,
            min_score=min_score,
        )

        suggestions = []
        if not results:
            common_tags: Dict[str, int] = {}
            for memo in memos[:50]:
                for tag in memo.get("tags", []):
                    common_tags[tag] = common_tags.get(tag, 0) + 1
            suggestions = [tag for tag, _ in sorted(common_tags.items(), key=lambda x: x[1], reverse=True)[:8]]

        return {
            "query": query,
            "candidates": len(memos),
            "results": results,
            "suggestions": suggestions,
            "rankingMethod": "tfidf+lsa-cosine",
            "nextStep": (
                "No strong match found. Try one of suggestions or widen query scope."
                if not results
                else "Use memo get <id> for full content of selected results."
            ),
        }

    # User endpoints
    def list_users(
        self,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
        filter_expr: Optional[str] = None,
        show_deleted: Optional[bool] = None,
    ) -> Dict[str, Any]:
        params = {
            "pageSize": page_size,
            "pageToken": page_token,
            "filter": filter_expr,
            "showDeleted": show_deleted,
        }
        return self._make_request("GET", "/api/v1/users", params=params)

    def get_user(self, user_id: str, read_mask: Optional[str] = None) -> Dict[str, Any]:
        user = normalize_user_id(user_id)
        params = {"readMask": read_mask}
        return self._make_request("GET", f"/api/v1/users/{user}", params=params)

    def get_user_setting(self, user_id: str, setting_id: str) -> Dict[str, Any]:
        user = normalize_user_id(user_id)
        return self._make_request("GET", f"/api/v1/users/{user}/settings/{setting_id}")

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        user = normalize_user_id(user_id)
        return self._make_request("GET", f"/api/v1/users/{user}:getStats")

    def list_user_settings(
        self,
        user_id: str,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        user = normalize_user_id(user_id)
        params = {"pageSize": page_size, "pageToken": page_token}
        return self._make_request("GET", f"/api/v1/users/{user}/settings", params=params)

    def list_user_notifications(
        self,
        user_id: str,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
        filter_expr: Optional[str] = None,
    ) -> Dict[str, Any]:
        user = normalize_user_id(user_id)
        params = {"pageSize": page_size, "pageToken": page_token, "filter": filter_expr}
        return self._make_request("GET", f"/api/v1/users/{user}/notifications", params=params)

    def list_user_webhooks(self, user_id: str) -> Dict[str, Any]:
        user = normalize_user_id(user_id)
        return self._make_request("GET", f"/api/v1/users/{user}/webhooks")

    # Activity endpoints
    def list_activities(
        self,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {"pageSize": page_size, "pageToken": page_token}
        return self._make_request("GET", "/api/v1/activities", params=params)

    def get_activity(self, activity_id: str) -> Dict[str, Any]:
        activity = normalize_activity_id(activity_id)
        return self._make_request("GET", f"/api/v1/activities/{activity}")

    # Attachment endpoints
    def list_attachments(
        self,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
        filter_expr: Optional[str] = None,
        order_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {
            "pageSize": page_size,
            "pageToken": page_token,
            "filter": filter_expr,
            "orderBy": order_by,
        }
        return self._make_request("GET", "/api/v1/attachments", params=params)

    def get_attachment(self, attachment_id: str) -> Dict[str, Any]:
        attachment = normalize_attachment_id(attachment_id)
        return self._make_request("GET", f"/api/v1/attachments/{attachment}")

    # Shortcut endpoints
    def list_shortcuts(self, user_id: str) -> Dict[str, Any]:
        user = normalize_user_id(user_id)
        return self._make_request("GET", f"/api/v1/users/{user}/shortcuts")

    def get_shortcut(self, user_id: str, shortcut_id: str) -> Dict[str, Any]:
        user = normalize_user_id(user_id)
        shortcut = normalize_shortcut_id(shortcut_id)
        return self._make_request("GET", f"/api/v1/users/{user}/shortcuts/{shortcut}")

    # Identity provider endpoints
    def list_identity_providers(self) -> Dict[str, Any]:
        return self._make_request("GET", "/api/v1/identity-providers")

    def get_identity_provider(self, provider_id: str) -> Dict[str, Any]:
        provider = normalize_identity_provider_id(provider_id)
        return self._make_request("GET", f"/api/v1/identity-providers/{provider}")

    # Instance endpoints
    def get_instance_profile(self) -> Dict[str, Any]:
        return self._make_request("GET", "/api/v1/instance/profile")


def redact_sensitive_fields(data: Any) -> Any:
    """Redact known secret fields in API responses."""
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            if key in {"accessToken", "clientSecret", "apiToken"}:
                redacted[key] = "***REDACTED***"
            elif key == "name" and isinstance(value, str) and "/accessTokens/" in value:
                redacted[key] = value.split("/accessTokens/")[0] + "/accessTokens/***REDACTED***"
            else:
                redacted[key] = redact_sensitive_fields(value)
        return redacted
    if isinstance(data, list):
        return [redact_sensitive_fields(item) for item in data]
    return data


def print_json(data: Any) -> None:
    print(json.dumps(redact_sensitive_fields(data), indent=2, ensure_ascii=False))


def require_double_confirmation(args: argparse.Namespace, action: str, target: str) -> None:
    """
    Enforce target-bound confirmation for every write operation.

    Must include --confirm-text exactly matching expected value.
    """
    expected = f"{action}:{target}"
    provided = (getattr(args, "confirm_text", "") or "").strip()
    if provided != expected:
        raise UseMemosError(
            "Target confirmation required. "
            f"Use --confirm-text '{expected}' exactly."
        )


def require_user_consent(consent_text: Optional[str]) -> None:
    """Require explicit user approval text for write actions."""
    text = (consent_text or "").strip()
    if len(text) < 2:
        raise UseMemosError(
            "Write operations require explicit user consent text. "
            "Provide --user-consent with a brief approval summary."
        )


def resolve_target_user_id(client: UseMemosClient, user_arg: Optional[str]) -> str:
    if user_arg:
        return normalize_user_id(user_arg)
    current = client.resolve_current_user()
    return normalize_user_id(current.get("name", ""))


def maybe_compact_memo_list(result: Dict[str, Any], compact: bool) -> Dict[str, Any]:
    if not compact:
        return result

    compacted = dict(result)
    memos = compacted.get("memos", [])
    compacted["memos"] = [compact_memo(memo) for memo in memos]
    return compacted


def error_payload(error_type: str, message: str, details: Optional[Any] = None, hint: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": False,
        "error": {
            "type": error_type,
            "message": message,
        },
    }
    if details is not None:
        payload["error"]["details"] = redact_sensitive_fields(details)
    if hint:
        payload["error"]["hint"] = hint
    return payload


def handle_auth_command(client: UseMemosClient, args: argparse.Namespace) -> Dict[str, Any]:
    if args.subcommand != "me":
        raise UseMemosError(f"Unsupported auth subcommand: {args.subcommand}")

    try:
        return client.get_current_user()
    except APIError:
        return {"user": client.resolve_current_user(), "source": "fallback"}


def handle_memo_command(client: UseMemosClient, args: argparse.Namespace) -> Dict[str, Any]:
    if args.subcommand == "list":
        result = client.list_memos(
            page_size=args.page_size,
            page_token=args.page_token,
            state=args.state,
            order_by=args.order_by,
            filter_expr=getattr(args, "filter", None),
            show_deleted=args.show_deleted,
        )
        return maybe_compact_memo_list(result, compact=args.compact)

    if args.subcommand == "get":
        return client.get_memo(args.memo_id)

    if args.subcommand == "create":
        require_user_consent(getattr(args, "user_consent", None))
        require_double_confirmation(args, "CREATE", "memo")
        created = client.create_memo(
            content=args.content,
            visibility=args.visibility,
            state=args.state,
            pinned=args.pinned,
            memo_id=args.memo_id,
        )
        current_user = client.resolve_current_user()
        if created.get("creator") != current_user.get("name"):
            raise UseMemosError("Write safety violation: created memo owner mismatch.")
        return created

    if args.subcommand == "update":
        require_user_consent(getattr(args, "user_consent", None))
        target = normalize_memo_id(args.memo_id)
        require_double_confirmation(args, "UPDATE", f"memos/{target}")
        client.require_owner_memo(target)
        pinned = None if args.pinned is None else args.pinned.lower() == "true"
        return client.update_memo(
            target,
            content=args.content,
            visibility=args.visibility,
            state=args.state,
            pinned=pinned,
        )

    if args.subcommand == "search":
        return client.search_memos(
            query=args.query,
            page_size=args.page_size,
            max_pages=args.max_pages,
            top_k=args.top_k,
            min_score=args.min_score,
            filter_expr=getattr(args, "filter", None),
            order_by=args.order_by,
        )

    if args.subcommand == "attachments":
        return client.list_memo_attachments(args.memo_id, page_size=args.page_size, page_token=args.page_token)

    if args.subcommand == "comments":
        return client.list_memo_comments(
            args.memo_id,
            page_size=args.page_size,
            page_token=args.page_token,
            order_by=args.order_by,
        )

    if args.subcommand == "relations":
        return client.list_memo_relations(args.memo_id, page_size=args.page_size, page_token=args.page_token)

    if args.subcommand == "reactions":
        return client.list_memo_reactions(args.memo_id, page_size=args.page_size, page_token=args.page_token)

    raise UseMemosError(f"Unsupported memo subcommand: {args.subcommand}")


def handle_user_command(client: UseMemosClient, args: argparse.Namespace) -> Dict[str, Any]:
    if args.subcommand == "list":
        try:
            return client.list_users(
                page_size=args.page_size,
                page_token=args.page_token,
                filter_expr=getattr(args, "filter", None),
                show_deleted=args.show_deleted,
            )
        except APIError as e:
            if e.status_code != 403:
                raise
            self_user = client.resolve_current_user()
            return {
                "users": [self_user],
                "nextPageToken": "",
                "totalSize": 1,
                "note": "Permission fallback: list users requires elevated permission; returned current user only.",
            }

    if args.subcommand == "get":
        return client.get_user(args.user_id, read_mask=args.read_mask)

    if args.subcommand == "stats":
        return client.get_user_stats(resolve_target_user_id(client, args.user_id))

    if args.subcommand == "setting":
        return client.get_user_setting(resolve_target_user_id(client, args.user_id), args.setting_id)

    if args.subcommand == "settings":
        return client.list_user_settings(
            resolve_target_user_id(client, args.user_id),
            page_size=args.page_size,
            page_token=args.page_token,
        )

    if args.subcommand == "notifications":
        return client.list_user_notifications(
            resolve_target_user_id(client, args.user_id),
            page_size=args.page_size,
            page_token=args.page_token,
            filter_expr=getattr(args, "filter", None),
        )

    if args.subcommand == "webhooks":
        return client.list_user_webhooks(resolve_target_user_id(client, args.user_id))

    raise UseMemosError(f"Unsupported user subcommand: {args.subcommand}")


def handle_activity_command(client: UseMemosClient, args: argparse.Namespace) -> Dict[str, Any]:
    if args.subcommand == "list":
        return client.list_activities(page_size=args.page_size, page_token=args.page_token)
    if args.subcommand == "get":
        return client.get_activity(args.activity_id)
    raise UseMemosError(f"Unsupported activity subcommand: {args.subcommand}")


def handle_attachment_command(client: UseMemosClient, args: argparse.Namespace) -> Dict[str, Any]:
    if args.subcommand == "list":
        return client.list_attachments(
            page_size=args.page_size,
            page_token=args.page_token,
            filter_expr=getattr(args, "filter", None),
            order_by=args.order_by,
        )
    if args.subcommand == "get":
        return client.get_attachment(args.attachment_id)
    raise UseMemosError(f"Unsupported attachment subcommand: {args.subcommand}")


def handle_shortcut_command(client: UseMemosClient, args: argparse.Namespace) -> Dict[str, Any]:
    if args.subcommand == "list":
        return client.list_shortcuts(resolve_target_user_id(client, args.user_id))
    if args.subcommand == "get":
        return client.get_shortcut(resolve_target_user_id(client, args.user_id), args.shortcut_id)
    raise UseMemosError(f"Unsupported shortcut subcommand: {args.subcommand}")


def handle_identity_provider_command(client: UseMemosClient, args: argparse.Namespace) -> Dict[str, Any]:
    if args.subcommand == "list":
        return client.list_identity_providers()
    if args.subcommand == "get":
        return client.get_identity_provider(args.provider_id)
    raise UseMemosError(f"Unsupported identity-provider subcommand: {args.subcommand}")


def handle_instance_command(client: UseMemosClient, args: argparse.Namespace) -> Dict[str, Any]:
    if args.subcommand == "profile":
        return client.get_instance_profile()
    raise UseMemosError(f"Unsupported instance subcommand: {args.subcommand}")


def execute_command(client: UseMemosClient, args: argparse.Namespace) -> Dict[str, Any]:
    handlers = {
        "auth": handle_auth_command,
        "memo": handle_memo_command,
        "user": handle_user_command,
        "activity": handle_activity_command,
        "attachment": handle_attachment_command,
        "shortcut": handle_shortcut_command,
        "identity-provider": handle_identity_provider_command,
        "instance": handle_instance_command,
    }
    handler = handlers.get(args.command)
    if handler is None:
        raise UseMemosError(f"Unsupported command: {args.command}")
    return handler(client, args)


def main() -> None:
    parser = CLIArgumentParser(
        description="Secure wrapper for usememos API operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--config", help="Path to config file (default: ~/.usememos/config.json)")
    parser.add_argument("--output", "-o", choices=["json", "text"], default="json", help="Output format")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Auth commands
    auth_parser = subparsers.add_parser("auth", help="Authentication operations")
    auth_subparsers = auth_parser.add_subparsers(dest="subcommand")
    auth_subparsers.add_parser("me", help="Get current user info")

    # Memo commands
    memo_parser = subparsers.add_parser("memo", help="Memo operations")
    memo_subparsers = memo_parser.add_subparsers(dest="subcommand")

    memo_list = memo_subparsers.add_parser("list", help="List memos")
    memo_list.add_argument("--page-size", type=int, help="Page size (max 1000)")
    memo_list.add_argument("--page-token", help="Page token for pagination")
    memo_list.add_argument("--state", choices=["STATE_UNSPECIFIED", "NORMAL", "ARCHIVED"], help="Memo state")
    memo_list.add_argument("--order-by", help='Order by field (e.g., "display_time desc")')
    memo_list.add_argument("--filter", help="Filter expression (CEL format)")
    memo_list.add_argument("--show-deleted", action="store_true", help="Show deleted memos")
    memo_list.add_argument("--compact", action="store_true", help="Token-efficient memo list output")

    memo_get = memo_subparsers.add_parser("get", help="Get a memo")
    memo_get.add_argument("memo_id", help="Memo ID or memos/<id>")

    memo_create = memo_subparsers.add_parser("create", help="Create a memo (write)")
    memo_create.add_argument("--content", required=True, help="Memo content (Markdown)")
    memo_create.add_argument("--visibility", choices=["PRIVATE", "PROTECTED", "PUBLIC"], default="PRIVATE")
    memo_create.add_argument("--state", choices=["NORMAL", "ARCHIVED"], default="NORMAL")
    memo_create.add_argument("--pinned", action="store_true", help="Set memo pinned")
    memo_create.add_argument("--memo-id", help="Optional custom memo id")
    memo_create.add_argument("--user-consent", help="Plain-text user approval summary")
    memo_create.add_argument("--confirm-text", help="Second confirmation text")

    memo_update = memo_subparsers.add_parser("update", help="Update a memo (write)")
    memo_update.add_argument("memo_id", help="Memo ID or memos/<id>")
    memo_update.add_argument("--content", help="Updated content")
    memo_update.add_argument("--visibility", choices=["PRIVATE", "PROTECTED", "PUBLIC"], help="Updated visibility")
    memo_update.add_argument("--state", choices=["NORMAL", "ARCHIVED"], help="Updated state")
    memo_update.add_argument("--pinned", choices=["true", "false"], help="Updated pinned")
    memo_update.add_argument("--user-consent", help="Plain-text user approval summary")
    memo_update.add_argument("--confirm-text", help="Second confirmation text")

    memo_search = memo_subparsers.add_parser("search", help="Semantic memo search (TF-IDF + LSA)")
    memo_search.add_argument("query", help="Search query")
    memo_search.add_argument("--page-size", type=int, default=20)
    memo_search.add_argument("--max-pages", type=int, default=2)
    memo_search.add_argument("--top-k", type=int, default=8)
    memo_search.add_argument("--min-score", type=float, default=0.15)
    memo_search.add_argument("--filter", help="Optional server-side filter")
    memo_search.add_argument("--order-by", default="pinned desc, display_time desc")

    memo_attachments = memo_subparsers.add_parser("attachments", help="List memo attachments")
    memo_attachments.add_argument("memo_id", help="Memo ID or memos/<id>")
    memo_attachments.add_argument("--page-size", type=int, help="Page size")
    memo_attachments.add_argument("--page-token", help="Page token")

    memo_comments = memo_subparsers.add_parser("comments", help="List memo comments")
    memo_comments.add_argument("memo_id", help="Memo ID or memos/<id>")
    memo_comments.add_argument("--page-size", type=int, help="Page size")
    memo_comments.add_argument("--page-token", help="Page token")
    memo_comments.add_argument("--order-by", help="Order by field")

    memo_relations = memo_subparsers.add_parser("relations", help="List memo relations")
    memo_relations.add_argument("memo_id", help="Memo ID or memos/<id>")
    memo_relations.add_argument("--page-size", type=int, help="Page size")
    memo_relations.add_argument("--page-token", help="Page token")

    memo_reactions = memo_subparsers.add_parser("reactions", help="List memo reactions")
    memo_reactions.add_argument("memo_id", help="Memo ID or memos/<id>")
    memo_reactions.add_argument("--page-size", type=int, help="Page size")
    memo_reactions.add_argument("--page-token", help="Page token")

    # User commands
    user_parser = subparsers.add_parser("user", help="User operations (read-only)")
    user_subparsers = user_parser.add_subparsers(dest="subcommand")

    user_list = user_subparsers.add_parser("list", help="List users")
    user_list.add_argument("--page-size", type=int, help="Page size")
    user_list.add_argument("--page-token", help="Page token")
    user_list.add_argument("--filter", help="Filter expression")
    user_list.add_argument("--show-deleted", action="store_true", help="Show deleted users")

    user_get = user_subparsers.add_parser("get", help="Get a user")
    user_get.add_argument("user_id", help="User ID / username / users/<id>")
    user_get.add_argument("--read-mask", help="Field mask")

    user_stats = user_subparsers.add_parser("stats", help="Get user stats")
    user_stats.add_argument("user_id", nargs="?", help="User ID (default: current user)")

    user_setting = user_subparsers.add_parser("setting", help="Get user setting")
    user_setting.add_argument("setting_id", help="Setting ID")
    user_setting.add_argument("--user-id", help="User ID (default: current user)")

    user_settings = user_subparsers.add_parser("settings", help="List user settings")
    user_settings.add_argument("user_id", nargs="?", help="User ID (default: current user)")
    user_settings.add_argument("--page-size", type=int, help="Page size")
    user_settings.add_argument("--page-token", help="Page token")

    user_notifications = user_subparsers.add_parser("notifications", help="List user notifications")
    user_notifications.add_argument("user_id", nargs="?", help="User ID (default: current user)")
    user_notifications.add_argument("--page-size", type=int, help="Page size")
    user_notifications.add_argument("--page-token", help="Page token")
    user_notifications.add_argument("--filter", help="Filter expression")

    user_webhooks = user_subparsers.add_parser("webhooks", help="List user webhooks")
    user_webhooks.add_argument("user_id", nargs="?", help="User ID (default: current user)")

    # Activity commands
    activity_parser = subparsers.add_parser("activity", help="Activity operations (read-only)")
    activity_subparsers = activity_parser.add_subparsers(dest="subcommand")

    activity_list = activity_subparsers.add_parser("list", help="List activities")
    activity_list.add_argument("--page-size", type=int, help="Page size")
    activity_list.add_argument("--page-token", help="Page token")

    activity_get = activity_subparsers.add_parser("get", help="Get an activity")
    activity_get.add_argument("activity_id", help="Activity ID or activities/<id>")

    # Attachment commands
    attachment_parser = subparsers.add_parser("attachment", help="Attachment operations (read-only)")
    attachment_subparsers = attachment_parser.add_subparsers(dest="subcommand")

    attachment_list = attachment_subparsers.add_parser("list", help="List attachments")
    attachment_list.add_argument("--page-size", type=int, help="Page size")
    attachment_list.add_argument("--page-token", help="Page token")
    attachment_list.add_argument("--filter", help="Filter expression")
    attachment_list.add_argument("--order-by", help="Order by field")

    attachment_get = attachment_subparsers.add_parser("get", help="Get an attachment")
    attachment_get.add_argument("attachment_id", help="Attachment ID or attachments/<id>")

    # Shortcut commands
    shortcut_parser = subparsers.add_parser("shortcut", help="Shortcut operations (read-only)")
    shortcut_subparsers = shortcut_parser.add_subparsers(dest="subcommand")

    shortcut_list = shortcut_subparsers.add_parser("list", help="List shortcuts")
    shortcut_list.add_argument("user_id", nargs="?", help="User ID (default: current user)")

    shortcut_get = shortcut_subparsers.add_parser("get", help="Get a shortcut")
    shortcut_get.add_argument("shortcut_id", help="Shortcut ID or shortcuts/<id>")
    shortcut_get.add_argument("--user-id", help="User ID (default: current user)")

    # Identity provider commands
    idp_parser = subparsers.add_parser("identity-provider", help="Identity provider operations (read-only)")
    idp_subparsers = idp_parser.add_subparsers(dest="subcommand")

    idp_subparsers.add_parser("list", help="List identity providers")
    idp_get = idp_subparsers.add_parser("get", help="Get an identity provider")
    idp_get.add_argument("provider_id", help="Provider ID")

    # Instance commands
    instance_parser = subparsers.add_parser("instance", help="Instance operations (read-only)")
    instance_subparsers = instance_parser.add_subparsers(dest="subcommand")

    instance_subparsers.add_parser("profile", help="Get instance profile")

    try:
        args = parser.parse_args()
        if not args.command:
            raise UseMemosError("No command provided. Use --help to see available commands.")
        client = UseMemosClient(args.config)
        print_json(execute_command(client, args))
    except ConfigurationError as e:
        print_json(
            error_payload(
                "configuration_error",
                str(e),
                hint="Set USEMEMOS_SITE_URL/USEMEMOS_API_TOKEN or provide ~/.usememos/config.json",
            )
        )
        sys.exit(1)
    except APIError as e:
        print_json(
            error_payload(
                "api_error",
                e.message,
                details={"statusCode": e.status_code, "response": e.details},
            )
        )
        sys.exit(1)
    except UseMemosError as e:
        print_json(error_payload("validation_error", str(e)))
        sys.exit(1)
    except Exception as e:
        print_json(error_payload("unexpected_error", str(e)))
        sys.exit(1)


if __name__ == "__main__":
    main()
