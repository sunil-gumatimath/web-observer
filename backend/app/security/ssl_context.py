import ssl
import sys

_cached_ssl_context: ssl.SSLContext | None = None


def get_ssl_context() -> ssl.SSLContext:
    global _cached_ssl_context
    if _cached_ssl_context is not None:
        return _cached_ssl_context

    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
    if sys.platform == "win32" and hasattr(ssl, "enum_certificates"):
        for store in ("ROOT", "CA", "MY"):
            try:
                for cert, enc, _trust in ssl.enum_certificates(store):
                    if enc == "x509_asn":
                        try:
                            ctx.load_verify_locations(
                                cadata=ssl.DER_cert_to_PEM_cert(cert)
                            )
                        except Exception:
                            pass
            except Exception:
                pass

    _cached_ssl_context = ctx
    return ctx
