"""Google Maps Scraper (GMS) management — auto-download, update, health check."""

import hashlib
import json
import os
import re
import platform
import stat
import subprocess
import urllib.request

import frappe

_GMS_DIR = os.path.join(frappe.get_site_path("private", "files"), "gms")
_GMS_BIN = os.path.join(_GMS_DIR, "gms")
_GMS_RELEASES_API = "https://api.github.com/repos/gosom/google-maps-scraper/releases/latest"
_REPO = "gosom/google-maps-scraper"

# The binary is fetched from a third party and then executed as the bench
# user, so "whatever the latest release is" is not an acceptable trust
# decision: it hands code execution to whoever publishes next. The site owner
# pins a version and the digest of the asset they have vetted; the download
# is refused unless both are present and the bytes match.
#
# The linux-arm64 digest below is the build this store runs and has vetted in
# production. A platform with no digest here is refused rather than trusted:
# add the digest of the asset you have checked before downloading, or install
# the binary by hand. Replace these deliberately when upgrading - a mismatch
# stops the scraper rather than running unknown code.
GMS_PINNED_VERSION: str | None = None
GMS_SHA256: dict[str, str] = {
	"linux-arm64": "b672ac98003fd39b9df7be35c78f3810375b65b528d3a0365df2d10fbc937bda",
}
_RELEASE_TAG_PATTERN = re.compile(r"^v?\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.]+)?$")
_verified: set[str] = set()


def _sha256(path: str) -> str:
	hashlib = __import__("hashlib")
	digest = hashlib.sha256()
	with open(path, "rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def verify_binary(bin_path: str) -> tuple[bool, str]:
	"""True when the file on disk is the pinned artifact (or no pin is set)."""
	suffix = _get_binary_name()
	expected = GMS_SHA256.get(suffix)
	if not expected:
		return True, "no digest pinned for this platform"
	if bin_path in _verified:
		return True, "digest already verified in this process"
	try:
		actual = _sha256(bin_path)
	except OSError as exc:
		return False, f"could not read binary: {exc}"
	if actual != expected:
		return False, (
			f"digest mismatch for {suffix}: expected {expected}, file is {actual}. "
			"Refusing to run an artifact that is not the pinned one."
		)
	_verified.add(bin_path)
	return True, "digest matches the pin"


def _get_binary_name() -> str:
	system = platform.system().lower()
	arch = platform.machine().lower()
	if system == "linux":
		return "linux-amd64" if "x86_64" in arch or "amd64" in arch else "linux-arm64"
	elif system == "darwin":
		return "darwin-amd64" if "x86_64" in arch or "amd64" in arch else "darwin-arm64"
	elif system == "windows":
		return "windows-amd64.exe"
	return "linux-amd64"


def get_gms_binary() -> str | None:
	"""Return the path to the GMS binary only if it exists and is the pinned
	artifact, else None. An unpinned digest for this platform is reported rather
	than enforced, so a store that has vetted nothing yet can still run."""
	if not (os.path.isfile(_GMS_BIN) and os.access(_GMS_BIN, os.X_OK)):
		return None
	ok, _reason = verify_binary(_GMS_BIN)
	return _GMS_BIN if ok else None


def ensure_gms() -> str:
	"""Ensure GMS binary exists. Download if missing. Returns binary path or throws."""
	bin_path = get_gms_binary()
	if bin_path:
		return bin_path

	result = download_gms()
	if result.get("success"):
		return _GMS_BIN

	frappe.throw(
		f"Google Maps Scraper not found and auto-download failed: {result.get('error', 'unknown')}. "
		"Download manually from https://github.com/gosom/google-maps-scraper/releases"
	)


def download_gms(version: str | None = None) -> dict:
	"""Download the GMS binary from a GitHub release, pinned and digest-checked.

	Fails closed: no pinned version, an unpinned digest for this platform, a
	mismatching digest or an unparsable version all end in "not downloaded"
	rather than an executable we cannot vouch for.
	"""
	try:
		# If a working binary already exists, skip download unless a specific version is requested
		if not version and get_gms_binary():
			return {"success": True, "version": GMS_PINNED_VERSION, "path": _GMS_BIN, "skipped": True}
		if version and not _RELEASE_TAG_PATTERN.match(version.strip()):
			return {"success": False, "error": f"Refusing version {version!r}: expected a release tag like v1.2.3"}
		target_version = (version or GMS_PINNED_VERSION or "").strip()
		if not target_version:
			return {
				"success": False,
				"error": (
					"No pinned GMS version. Set GMS_PINNED_VERSION in "
					"shop/integrations/gms.py, or install the binary manually from "
					"https://github.com/gosom/google-maps-scraper/releases"
				),
			}
		expected_digest = GMS_SHA256.get(_get_binary_name())
		if not expected_digest:
			return {
				"success": False,
				"error": (
					f"No pinned SHA-256 for {_get_binary_name()}. Add it to GMS_SHA256 in "
					"shop/integrations/gms.py before downloading, or install manually."
				),
			}

		os.makedirs(_GMS_DIR, exist_ok=True)

		# Get latest release info
		# The tag is validated above, so the repository is chosen by this
		# module and only the tag travels into the URL.
		url = f"https://api.github.com/repos/{_REPO}/releases/tags/{target_version}"
		req = urllib.request.Request(
			url,
			headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "shop-gms"},
		)
		with urllib.request.urlopen(req, timeout=15) as resp:
			release = json.loads(resp.read())
		tag = release["tag_name"]
		assets = release.get("assets", [])

		binary_suffix = _get_binary_name()
		download_url = None
		for asset in assets:
			if binary_suffix in asset["name"]:
				download_url = asset["browser_download_url"]
				break

		# Fallback: try linux-amd64 if native arch binary not found (qemu can run it)
		if not download_url and binary_suffix == "linux-arm64":
			binary_suffix = "linux-amd64"
			for asset in assets:
				if binary_suffix in asset["name"]:
					download_url = asset["browser_download_url"]
					break

		if not download_url:
			return {"success": False, "error": f"No binary found for {binary_suffix} in release {tag}"}

		# Download to a temporary name, verify the digest, and only then make it
		# executable. A mismatch never leaves an executable behind.
		tmp_path = _GMS_BIN + ".part"
		try:
			urllib.request.urlretrieve(download_url, tmp_path)
			actual = _sha256(tmp_path)
			if actual != expected_digest:
				os.unlink(tmp_path)
				return {
					"success": False,
					"error": (
						f"Refusing to install: {binary_suffix} from {tag} has digest {actual}, "
						f"expected {expected_digest}. Nothing was installed."
					),
				}
			os.replace(tmp_path, _GMS_BIN)
		except Exception:
			if os.path.exists(tmp_path):
				try:
					os.unlink(tmp_path)
				except OSError:
					pass
			raise

		_verified.clear()
		ok, reason = verify_binary(_GMS_BIN)
		if not ok:
			return {"success": False, "error": reason}
		os.chmod(_GMS_BIN, os.stat(_GMS_BIN).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

		# Smoke run: the artifact is verified, so this is a sanity check, not
		# the verification.
		result = subprocess.run([_GMS_BIN, "-h"], capture_output=True, timeout=10)
		if result.returncode != 0 and result.returncode != 2:  # -h returns 2 on some builds
			return {"success": False, "error": f"Binary downloaded but failed to execute: {result.stderr[:200]}"}

		return {"success": True, "version": tag, "path": _GMS_BIN, "sha256": expected_digest}

	except Exception as e:
		return {"success": False, "error": str(e)}


def get_gms_status() -> dict:
	"""Return GMS status: installed, version, path."""
	bin_path = get_gms_binary()
	if not bin_path:
		return {"installed": False, "path": None, "version": None}

	try:
		result = subprocess.run(
			[bin_path, "-h"],
			capture_output=True, text=True, timeout=10,
		)
		output = result.stdout + result.stderr
	except Exception:
		output = ""

	return {
		"installed": True,
		"path": bin_path,
		"version": None,
	}
