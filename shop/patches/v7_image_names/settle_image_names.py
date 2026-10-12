"""Settle product image names that were stuck renaming themselves forever.

Runs post_model_sync. Touches only file names and the rows that point at them -
no product, price, stock or copy changes.

Three faults, one cause. `shop.files.rename_product_images` gives each image the
name `{slug}-{n}` on save, and asks Frappe's `generate_file_name` for it. That
helper only returns the clean name when nothing is on disk under it, so:

  1. Replacing or removing a photo dropped the `Shop Product Image` row and left
     the file behind. Nothing reclaimed it, so the `{slug}-{n}` slot the *next*
     photo at that position wanted was permanently occupied.
  2. A taken slot made `generate_file_name` append a six-character collision
     hash, producing `{slug}-{n}<hash>.webp`.
  3. `already_named` only matched `{slug}-{n}.ext`, so that hashed name did not
     count as named. Every later save renamed the image again, to a fresh hash,
     changing its url each time.

The visible effects were an image that uploaded fine and then rendered as
another product's picture or not at all, and a file list that grew without
bound. Both are now prevented at upload and save time; this puts the existing
catalogue back in order.

Reclaimed first are the files that are genuinely unreferenced - that is what
frees the slots, and it is also why the renames below can land on clean names
rather than collecting another hash. A file anything still points at is left
alone, so nothing another product, a collection, the shop logo or a variant
depends on is removed.

Re-running is a no-op: a name that already matches is skipped.
"""

import os

import frappe

from shop.files import (
	_names_in_namespace,
	_public_or_private_url,
	_referenced_elsewhere,
	_repoint,
	site_file_path,
)

PRIVATE_PREFIX = "/private/files/"

# Rows whose file is not on disk. Recorded rather than guessed at: a missing
# image has to be re-uploaded by whoever owns the product, and inventing a
# replacement here would put a picture on the storefront nobody chose.
_missing: list[str] = []

# Rows that list the same file twice. Reported, never renamed - see below.
_duplicates: list[str] = []

# Reclaimed paths whose bytes are still waiting to be unlinked after the commit.
# Keyed by absolute path, which is what a rename targets.
_reclaimed: dict[str, str] = {}


def missing_images() -> list[str]:
	"""Image rows whose bytes are not on disk, as found by the last run."""
	return list(_missing)


def duplicate_images() -> list[str]:
	"""Image rows that list the same file twice, as found by the last run."""
	return list(_duplicates)


def execute() -> None:
	"""Reclaim unreferenced product images, then settle the names.

	Settling frees the names the renames need, so it can take a second pass to
	finish: a row that was blocked by another row's file moves on the next run,
	once that row has moved itself. It converges, and a further run does nothing.
	"""
	_missing.clear()
	_duplicates.clear()
	_reclaimed.clear()
	freed = reclaim_unreferenced_images()
	settled = settle_image_names()
	if freed or settled or _missing or _duplicates:
		frappe.msgprint(
			f"reloop: reclaimed {len(freed)} orphaned product image file(s),"
			f" settled {len(settled)} image name(s)"
			f"{_missing_note()}{_duplicates_note()}",
			alert=True,
		)


def _missing_note() -> str:
	if not _missing:
		return ""
	detail = "\n".join(_missing)
	frappe.log_error(
		title="Product image has no file on disk",
		message="These image rows point at files that are not on disk. Re-upload"
		f" the photo on the product, or remove the row:\n{detail}",
	)
	return f"; {len(_missing)} row(s) still have no file and need re-uploading"


def _duplicates_note() -> str:
	if not _duplicates:
		return ""
	detail = "\n".join(_duplicates)
	frappe.log_error(
		title="Product lists the same image twice",
		message="These rows point at one file, so the photo is shown twice. Remove"
		f" or replace the repeat in the product's image list:\n{detail}",
	)
	return f"; {len(_duplicates)} duplicated image row(s) left as they are"


def reclaim_unreferenced_images() -> list[str]:
	"""Delete product-namespace files nothing points at any more.

	Scoped to `{slug}-{n}` names of products that exist, so a Meta conversion
	cache or an unrelated upload in the same folder is never a candidate. That
	matters here: `meta_catalog` writes `meta-...` files into the same directory
	and Meta's own catalogue holds those urls, so they are not ours to delete
	here even though nothing in this database references them.
	"""
	slugs = [r.slug for r in frappe.get_all("Shop Product", fields=["slug"]) if r.slug]
	if not slugs:
		return []

	freed: list[str] = []
	for slug in sorted(set(slugs)):
		for name in sorted(_names_in_namespace(slug)):
			url = _public_or_private_url(name)
			if not url or _referenced_elsewhere(url):
				continue
			path = site_file_path(url)
			if not path or not os.path.isfile(path):
				continue
			try:
				frappe.delete_doc("File", {"file_url": url}, ignore_permissions=True, force=True)
			except Exception:
				frappe.log_error(
					title="Orphaned product image could not be deleted",
					message=f"{url}: {frappe.get_traceback()}",
				)
				continue
			# Bytes after the commit, for the same reason as in files.py: the
			# delete above rolls back with the transaction, and unlinking inside
			# it would leave a row pointing at bytes an exception had destroyed.
			# Recorded in `_reclaimed` so a rename that later takes this very path
			# can cancel the delete - the file there is then the new image, not
			# the leftover.
			#
			# Absolute, and it must match what `_rename_one` keys on exactly.
			# `site_file_path` is relative whenever the bench is driven from the
			# sites directory, so a relative key here would silently never match
			# the rename's absolute target: the guard would miss, the queued
			# unlink would fire, and it would delete the image that had just
			# been renamed into that path.
			_reclaimed[os.path.abspath(path)] = _stamp(path)
			frappe.db.after_commit.add(lambda p=os.path.abspath(path): _finish_reclaim(p))
			freed.append(name)
	return freed


def _stamp(path: str) -> tuple | None:
	"""Size and mtime of `path`, as the thing a later delete has to match."""
	try:
		info = os.stat(path)
	except OSError:
		return None
	return (info.st_size, info.st_mtime_ns)


def _finish_reclaim(path: str) -> None:
	"""Unlink a reclaimed file, unless something else now occupies its path.

	The path alone is not enough to identify the leftover. A rename onto this
	path legitimately replaces the file - that is the whole point of reclaiming
	first - and then the queued delete must not run, or it removes the image
	that was just renamed into place. Size and mtime are compared as well, so
	only the exact bytes that were reclaimed are ever unlinked, whatever else
	has happened to the path since.
	"""
	if path not in _reclaimed:
		return
	if _stamp(path) != _reclaimed[path]:
		_reclaimed.pop(path, None)
		return
	_reclaimed.pop(path, None)
	_unlink(path)


def settle_image_names() -> list[str]:
	"""Rename every image that is not sitting on its exact `{slug}-{n}` name.

	Deliberately stricter than `already_named`, which also accepts the
	collision-hashed form so that a *save* leaves a settled image alone. A
	one-time repair wants the canonical name rather than merely a stable one:
	`{slug}-{n}` is what the file list is supposed to read, and the hashed
	names are the visible scar of the churn. A name already exactly
	`{slug}-{n}.ext` is skipped, so a second run does nothing.
	"""
	settled: list[str] = []
	rows = frappe.get_all(
		"Shop Product Image",
		fields=["name", "parent", "idx", "image"],
		order_by="parent asc, idx asc",
	)
	by_product: dict[str, list] = {}
	for row in rows:
		by_product.setdefault(row.parent, []).append(row)

	slugs = {
		r.name: r.slug
		for r in frappe.get_all("Shop Product", fields=["name", "slug"])
	}

	for parent, images in by_product.items():
		slug = (slugs.get(parent) or "").strip()
		if not slug:
			continue
		# Numbered exactly as rename_product_images numbers them: over the rows
		# that actually carry an image, so the index here is the index the next
		# save would use and the names agree.
		numbered = [row for row in images if (row.image or "").strip()]

		# Urls listed by more than one row, found before anything is moved.
		# `_repoint` follows every row holding the old url, so renaming one copy
		# of a duplicated file drags the other with it: the patch renames, finds
		# them swapped, renames back, and never converges. Both rows already
		# render, so the repeat is left exactly as it is and reported instead -
		# dropping or replacing it is the merchant's call about their listing,
		# not a naming decision this patch should make for them.
		repeated: dict[str, list[int]] = {}
		for index, row in enumerate(numbered, start=1):
			repeated.setdefault(row.image.strip(), []).append(index)
		duplicated = {url for url, idxs in repeated.items() if len(idxs) > 1}
		for url in sorted(duplicated):
			_duplicates.append(f"{parent} rows {repeated[url]}: {url}")

		for index, row in enumerate(numbered, start=1):
			url = row.image.strip()
			if url.startswith("http") or url in duplicated:
				continue
			name = os.path.basename(url)
			extension = os.path.splitext(name)[1].lower() or ".webp"
			if name == f"{slug}-{index}{extension}":
				continue
			path = site_file_path(url)
			if not path or not os.path.isfile(path):
				# The row points at bytes that are gone. There is nothing to
				# rename and nothing to point it at, so it is reported by the
				# storefront's own missing-image check rather than guessed at.
				_missing.append(f"{parent}#{row.idx}: {url}")
				continue
			if _rename_one(url, path, slug, index):
				settled.append(f"{parent}#{row.idx}: {name}")

	return settled


def _rename_one(old_url: str, path: str, slug: str, index: int) -> bool:
	"""Move one image onto its clean `{slug}-{n}` name. True when it moved.

	The clean name is preferred over `generate_file_name`, because the file that
	was occupying this slot was reclaimed by `reclaim_unreferenced_images` and
	its bytes are only unlinked after the commit - so it still exists right now
	and `generate_file_name` would hand back another collision hash, freezing
	the churn this patch exists to end. `os.replace` overwrites it atomically
	and the queued unlink is for the reclaimed path only, so the two cannot
	collide: the reclaimed file has no File row and no referencing row, so
	nothing else can claim that name.
	"""
	path = os.path.abspath(path)
	directory = os.path.dirname(path)
	extension = os.path.splitext(os.path.basename(path))[1].lower() or ".webp"
	private = old_url.startswith(PRIVATE_PREFIX)
	prefix = PRIVATE_PREFIX if private else "/files/"
	name = f"{slug}-{index}{extension}"
	target = os.path.abspath(os.path.join(directory, name))

	if _is_taken(target, old_url, private):
		# Something is still using that name - usually another row of this same
		# product sitting at a different index, which is about to be renamed in
		# its own turn. Overwriting would hand that row the wrong picture, so
		# this one takes a collision name instead and settles on a later run.
		from frappe.core.doctype.file.utils import generate_file_name

		name = generate_file_name(name, is_private=private)
		target = os.path.abspath(os.path.join(directory, name))

	if target == path:
		return False

	original = os.stat(path)
	os.replace(path, target)
	# The bytes that were at `target` are now this image's, so a queued unlink
	# for a reclaimed file sitting on that path must not fire.
	_reclaimed.pop(target, None)
	_restore(target, original)

	prefix = PRIVATE_PREFIX if private else "/files/"
	# _repoint moves the File rows and every storefront row holding the old url,
	# which is this product's row and any other that shares the image.
	_repoint(old_url, f"{prefix}{name}", name, os.path.getsize(target))
	return True


def _is_taken(target: str, old_url: str, private: bool) -> bool:
	"""True when a file already sits at `target` and some row still needs it.

	A file nothing references is not a blocker: `reclaim_unreferenced_images`
	has already released it, and its bytes are only unlinked after the commit -
	so it is still on disk here, which is exactly why this cannot be a plain
	`os.path.exists` test. A file that some row still points at is a real
	blocker and must not be overwritten.
	"""
	if not os.path.exists(target):
		return False
	url = f"{PRIVATE_PREFIX if private else '/files/'}{os.path.basename(target)}"
	if url == old_url:
		return False
	if _referenced_elsewhere(url):
		return True
	return bool(
		frappe.db.sql("select name from `tabShop Product Image` where image=%s limit 1", (url,))
	)


def _restore(path: str, original: os.stat_result) -> None:
	"""Give the replacement the original file's ownership and permissions."""
	try:
		os.chown(path, original.st_uid, original.st_gid)
	except (OSError, AttributeError):
		pass
	try:
		os.chmod(path, original.st_mode & 0o7777)
	except OSError:
		pass


def _unlink(path: str) -> None:
	if path and os.path.exists(path):
		try:
			os.remove(path)
		except OSError:
			pass
