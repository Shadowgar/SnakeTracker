# Deliberately based on the existing Pi release; adds only backup code/tooling.
# Verify the base image ID/revision and the detached source diff before building.
ARG BACKUP_BASE_IMAGE=snaketracker:m66b-profile-c4740b3
FROM ${BACKUP_BASE_IMAGE}
ARG SNAKETRACKER_BUILD_GIT_SHA
ARG SNAKETRACKER_UID=1001
ENV SNAKETRACKER_BUILD_GIT_SHA=${SNAKETRACKER_BUILD_GIT_SHA}
LABEL org.opencontainers.image.revision=${SNAKETRACKER_BUILD_GIT_SHA} \
      org.snaketracker.backup-only="true" \
      org.snaketracker.backup-base-revision="c4740b32c1b80f054725c0a037d47689bc283474"
COPY --chown=${SNAKETRACKER_UID}:${SNAKETRACKER_UID} --chmod=0444 src/snaketracker/infrastructure/backups/pipeline.py /app/src/snaketracker/infrastructure/backups/pipeline.py
COPY --chown=${SNAKETRACKER_UID}:${SNAKETRACKER_UID} --chmod=0444 src/snaketracker/infrastructure/backups/pipeline.py /app/.venv/lib/python3.13/site-packages/snaketracker/infrastructure/backups/pipeline.py
COPY --chown=${SNAKETRACKER_UID}:${SNAKETRACKER_UID} --chmod=0444 scripts/qualification/backup_worker_once.py /app/qualification/backup_worker_once.py
CMD ["python", "/app/qualification/backup_worker_once.py"]
