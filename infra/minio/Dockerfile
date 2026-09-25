# Build MinIO from source so the repository does not need to store
# a large architecture-specific binary.
FROM golang:1.24-alpine AS builder

ARG MINIO_VERSION=RELEASE.2025-10-15T17-29-55Z

RUN apk add --no-cache ca-certificates git

ENV CGO_ENABLED=0

RUN go install github.com/minio/minio@${MINIO_VERSION}

FROM alpine:3.20

RUN apk add --no-cache ca-certificates

COPY --from=builder /go/bin/minio /usr/local/bin/minio

RUN chmod +x /usr/local/bin/minio

EXPOSE 9000 9001

ENTRYPOINT ["minio"]
