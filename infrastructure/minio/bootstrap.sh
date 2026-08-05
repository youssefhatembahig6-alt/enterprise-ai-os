#!/bin/sh
# Create the object-storage bucket and deny anonymous access.
#
# Keys are namespaced {company}/{classification}/{document_type}/{filename}
# (spec FR-039), so one tenant's objects can never be enumerated from another's
# prefix. This script only creates the bucket; the prefix convention is enforced
# by eaios_core.keys, which refuses to build an unattributable key at all.

set -eu

MINIO_ALIAS=local
MINIO_URL="http://${MINIO_HOST:-minio}:9000"
BUCKET="${MINIO_BUCKET:-eaios}"

echo "Waiting for MinIO at ${MINIO_URL}..."
until mc alias set "${MINIO_ALIAS}" "${MINIO_URL}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" >/dev/null 2>&1; do
    sleep 1
done

if mc ls "${MINIO_ALIAS}/${BUCKET}" >/dev/null 2>&1; then
    echo "Bucket ${BUCKET} already exists."
else
    mc mb "${MINIO_ALIAS}/${BUCKET}"
    echo "Created bucket ${BUCKET}."
fi

# No anonymous access, ever. Download URLs are short-lived and issued only after
# an authorization check (which arrives with the auth feature).
mc anonymous set none "${MINIO_ALIAS}/${BUCKET}"

echo "MinIO bootstrap complete."
