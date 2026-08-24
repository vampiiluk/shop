"""Google Maps Scraper (GMS) management — auto-download, update, health check."""

import json
import os
import platform
import stat
import subprocess
import urllib.request

import frappe

_GMS_DIR = os.path.join(frappe.get_site_path("private", "files"), "gms")
_GMS_BIN = os.path.join(_GMS_DIR, "gms")
_GMS_RELEASES_API = "https://api.github.com/repos/gosom/google-maps-scraper/releases/latest"


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
	"""Return the path to the GMS binary if it exists, else None."""
	if os.path.isfile(_GMS_BIN) and os.access(_GMS_BIN, os.X_OK):
		return _GMS_BIN
	return None


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
	"""Download GMS binary from GitHub releases. Returns dict with success/error."""
	try:
		os.makedirs(_GMS_DIR, exist_ok=True)

		# Get latest release info
		if not version:
			req = urllib.request.Request(
				_GMS_RELEASES_API,
				headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "shop-gms"},
			)
			with urllib.request.urlopen(req, timeout=15) as resp:
				release = json.loads(resp.read())
			tag = release["tag_name"]
			assets = release.get("assets", [])
		else:
			url = f"https://api.github.com/repos/gosom/google-maps-scraper/releases/tags/{version}"
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

		if not download_url:
			return {"success": False, "error": f"No binary found for {binary_suffix} in release {tag}"}

		# Download binary
		urllib.request.urlretrieve(download_url, _GMS_BIN)
		os.chmod(_GMS_BIN, os.stat(_GMS_BIN).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

		# Verify it works
		result = subprocess.run([_GMS_BIN, "-h"], capture_output=True, timeout=10)
		if result.returncode != 0 and result.returncode != 2:  # -h returns 2 on some builds
			return {"success": False, "error": f"Binary downloaded but failed to execute: {result.stderr[:200]}"}

		return {"success": True, "version": tag, "path": _GMS_BIN}

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
