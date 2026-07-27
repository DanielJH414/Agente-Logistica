from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable

import oci


SUPPORTED_EXTENSIONS = {
	".pdf",
	".docx",
	".xlsx",
	".xls",
	".csv",
	".txt",
	".md",
	".json",
	".xml",
	".yaml",
	".yml",
}

DEFAULT_NAMESPACE = "axtvg0vgl5uf"
DEFAULT_BUCKET = "Documentos-Nexus"
DEFAULT_REGION = "sa-bogota-1"
DEFAULT_PROFILE = "DEFAULT"


def _config_value(name: str, default: str) -> str:
	value = os.getenv(name, "").strip()
	if value:
		return value
	try:
		import streamlit as st
		secrets = getattr(st, "secrets", None)
		if secrets:
			secret_value = secrets.get(name, "")
			if isinstance(secret_value, str):
				return secret_value.strip()
	except Exception:
		pass
	return default.strip()


def _safe_relative_path(object_name: str, prefix: str) -> Path | None:
	"""Convierte una clave OCI en una ruta local segura y relativa."""
	normalized_name = object_name.replace("\\", "/").lstrip("/")
	normalized_prefix = prefix.replace("\\", "/").strip("/")
	if normalized_prefix:
		if normalized_name == normalized_prefix:
			return None
		prefix_with_separator = f"{normalized_prefix}/"
		if not normalized_name.startswith(prefix_with_separator):
			return None
		normalized_name = normalized_name[len(prefix_with_separator) :]

	parts = PurePosixPath(normalized_name).parts
	if not parts or any(part in {"", ".", ".."} for part in parts):
		return None
	return Path(*parts)


def _iter_objects(client: Any, namespace: str, bucket: str, prefix: str) -> Iterable[Any]:
	start = None
	while True:
		response = client.list_objects(
			namespace,
			bucket,
			prefix=prefix or None,
			fields="name,size,etag,timeModified",
			start=start,
		)
		objects = response.data.objects or []
		yield from objects
		start = response.data.next_start_with
		if not start:
			break


def sync_object_storage(local_folder: str | Path) -> Dict[str, int]:
	"""Replica el bucket de OCI en la carpeta local usada por el pipeline."""
	local_root = Path(local_folder).resolve()
	local_root.mkdir(parents=True, exist_ok=True)

	namespace = _config_value("OCI_NAMESPACE", DEFAULT_NAMESPACE)
	bucket = _config_value("OCI_BUCKET", DEFAULT_BUCKET)
	region = _config_value("OCI_REGION", DEFAULT_REGION)
	profile = _config_value("OCI_PROFILE", DEFAULT_PROFILE)
	prefix = _config_value("OCI_PREFIX", "").strip("/")

	is_production = os.getenv("ENVIRONMENT") == "production"
	try:
		if is_production:
			try:
				signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
				client = oci.object_storage.ObjectStorageClient(config={'region':region}, signer=signer)
			except Exception as e:
				print(f"Error al crear el cliente de OCI con Instance Principals: {e}")
				raise e
		else:
			config_file = os.getenv("OCI_CONFIG_FILE", "").strip() or os.path.expanduser("~/.oci/config")
			if os.path.exists(config_file):
				config = oci.config.from_file(file_location=config_file, profile_name=profile)
				config["region"] = region
				client = oci.object_storage.ObjectStorageClient(config)
				print("Autenticación OCI: Usando ~/.oci/config (Local)")
			else:
				print("Autenticación OCI: no se encontró ~/.oci/config; se omite la sincronización con el bucket")
				return {"downloaded": 0, "updated": 0, "unchanged": 0, "deleted": 0, "skipped": 0, "error": "OCI config not found"}
	except Exception as exc:
		print(f"No se pudo inicializar OCI: {exc}")
		return {"downloaded": 0, "updated": 0, "unchanged": 0, "deleted": 0, "skipped": 0, "error": str(exc)}
		
	remote_paths: set[Path] = set()
	summary = {"downloaded": 0, "updated": 0, "unchanged": 0, "deleted": 0, "skipped": 0}

	for object_info in _iter_objects(client, namespace, bucket, prefix):
		relative_path = _safe_relative_path(object_info.name, prefix)
		if relative_path is None or relative_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
			summary["skipped"] += 1
			continue

		remote_paths.add(relative_path)
		destination = local_root / relative_path
		destination.parent.mkdir(parents=True, exist_ok=True)
		current_etag_path = destination.with_name(f".{destination.name}.oci-etag")
		remote_etag = (object_info.etag or "").strip('"')
		current_etag = current_etag_path.read_text(encoding="utf-8").strip() if current_etag_path.exists() else ""

		if destination.exists() and current_etag and current_etag == remote_etag:
			summary["unchanged"] += 1
			continue

		response = client.get_object(namespace, bucket, object_info.name)
		temporary_path = destination.with_name(f".{destination.name}.oci-download")
		try:
			with temporary_path.open("wb") as handle:
				shutil.copyfileobj(response.data.raw, handle)
			temporary_path.replace(destination)
			current_etag_path.write_text(remote_etag, encoding="utf-8")
		finally:
			if temporary_path.exists():
				temporary_path.unlink()

		summary["updated" if destination.exists() and current_etag else "downloaded"] += 1

	for path in local_root.rglob("*"):
		if not path.is_file() or path.name.endswith(".oci-etag"):
			continue
		relative_path = path.relative_to(local_root)
		if relative_path not in remote_paths:
			path.unlink()
			etag_path = path.with_name(f".{path.name}.oci-etag")
			if etag_path.exists():
				etag_path.unlink()
			summary["deleted"] += 1

	for etag_path in local_root.rglob("*.oci-etag"):
		document_name = etag_path.name.removeprefix(".").removesuffix(".oci-etag")
		document_path = etag_path.with_name(document_name)
		if not document_path.exists():
			etag_path.unlink()

	return summary

