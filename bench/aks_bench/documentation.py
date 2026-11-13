"""Read-only, logged Microsoft Learn access from the host, never Azure management."""

import hashlib
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

VERSION_URL = "https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/error-codes/nodepoolmcversionincompatible-error"
PROVIDER_URL = "https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-register-resource-provider"
NAMESPACE_URL = "https://learn.microsoft.com/en-us/azure/aks/managed-namespaces"
NAMESPACE_CONCEPTS_URL = "https://learn.microsoft.com/en-us/azure/aks/concepts-managed-namespaces"


def approved(url):
    parsed = urlparse(url)
    return (parsed.scheme == "https" and parsed.hostname == "learn.microsoft.com"
            and parsed.port in (None, 443) and not parsed.username and not parsed.password
            and (parsed.path.startswith(("/en-us/azure/", "/en-us/troubleshoot/azure/", "/en-us/cli/azure/"))
                 or parsed.path == "/api/search"))


class RestrictedRedirect(HTTPRedirectHandler):
    def __init__(self, metrics):
        self.requests = 1
        self.metrics = metrics

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not approved(newurl):
            raise ValueError("documentation redirect outside approved Microsoft Learn paths")
        self.requests += 1
        self.metrics["documentation_http_requests"] = self.requests
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch(argv, directory=None, metrics=None):
    """Support GET-only curl flags and save public response bodies for audit."""
    urls = []
    for arg in argv:
        if arg.startswith("https://"):
            urls.append(arg)
        elif arg not in ("-s", "-S", "-L", "-f", "-sS", "-sSL", "-fsSL", "-fsS", "-SL",
                          "--silent", "--show-error", "--location", "--fail"):
            raise ValueError("documentation curl supports GET URLs and -s/-S/-L/-f; use shell redirection for files")
    if len(urls) != 1 or not approved(urls[0]):
        raise ValueError("only read-only Microsoft Learn documentation/search URLs are permitted")
    metrics = metrics if metrics is not None else {}
    redirects = RestrictedRedirect(metrics)
    request = Request(urls[0], headers={"User-Agent": "AKS-Skills-Benchmark/1.0", "Accept": "text/markdown, text/html;q=0.9"})
    metrics.update(url=urls[0], documentation_http_requests=1,
                   documentation_search=urlparse(urls[0]).path == "/api/search")
    with build_opener(redirects).open(request, timeout=20) as response:
        body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ValueError("documentation response exceeds 2 MiB limit")
        text = body.decode("utf-8", errors="replace")
        status = response.status
    digest = hashlib.sha256(body).hexdigest()
    if directory:
        directory = Path(directory)
        directory.mkdir(exist_ok=True, parents=True)
        (directory / f"{digest}.txt").write_text(text)
    return text, {"url": urls[0], "http_status": status, "document_sha256": digest,
                  "documentation_http_requests": redirects.requests,
                  "documentation_search": urlparse(urls[0]).path == "/api/search"}
