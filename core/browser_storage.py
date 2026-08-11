from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core.kernel_cdp_session import KernelCDPSession


@dataclass(frozen=True)
class BrowserStorageSnapshot:
    storage_type: str
    origin: str
    token: str = field(repr=False)
    record: dict[str, Any]

    @property
    def token_present(self) -> bool:
        return bool(self.token)


class BrowserStorageInspector:
    def __init__(self, session: KernelCDPSession, cookie_name: str = "dicloak_auth"):
        self.session = session
        self.cookie_name = cookie_name

    def read_cookie(self, url: str | None = None) -> BrowserStorageSnapshot:
        current_url = url or self.session.current_url
        result = self.session.command("Network.getCookies", {"urls": [current_url]})
        cookies = result.get("cookies", []) if isinstance(result, dict) else []
        record = next(
            (item for item in cookies if isinstance(item, dict) and item.get("name") == self.cookie_name),
            {},
        )
        return BrowserStorageSnapshot(
            storage_type="cookie",
            origin=_origin(current_url),
            token=str(record.get("value", "")),
            record=dict(record),
        )

    def read_local_storage(self, key: str = "dicloak_auth") -> BrowserStorageSnapshot:
        raw = self.session.evaluate(f"localStorage.getItem({json.dumps(key)})")
        record = _json_object(raw)
        return BrowserStorageSnapshot(
            storage_type="localstorage",
            origin=_origin(self.session.current_url),
            token=str(record.get("token", "")),
            record=record,
        )

    def read_indexed_db(
        self,
        database_name: str = "dicloak_auth",
        store_name: str = "sessions",
        record_key: str = "current",
    ) -> BrowserStorageSnapshot:
        record = self.session.evaluate(
            """
            new Promise(async (resolve, reject) => {
              try {
                if (typeof indexedDB.databases !== 'function') {
                  reject(new Error('indexedDB.databases is unavailable for read-only inspection'));
                  return;
                }
                const databases = await indexedDB.databases();
                if (!databases.some(item => item.name === %s)) { resolve(null); return; }
                const request = indexedDB.open(%s);
                request.onerror = () => reject(request.error);
                request.onsuccess = () => {
                  const db = request.result;
                  if (!db.objectStoreNames.contains(%s)) { db.close(); resolve(null); return; }
                  const tx = db.transaction(%s, 'readonly');
                  const get = tx.objectStore(%s).get(%s);
                  get.onsuccess = () => resolve(get.result || null);
                  get.onerror = () => reject(get.error);
                  tx.oncomplete = () => db.close();
                };
              } catch (error) { reject(error); }
            })
            """
            % tuple(
                json.dumps(value)
                for value in (
                    database_name,
                    database_name,
                    store_name,
                    store_name,
                    store_name,
                    record_key,
                )
            )
        )
        normalized = record if isinstance(record, dict) else {}
        return BrowserStorageSnapshot(
            storage_type="indexeddb",
            origin=_origin(self.session.current_url),
            token=str(normalized.get("token", "")),
            record=dict(normalized),
        )


def _json_object(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _origin(url: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
