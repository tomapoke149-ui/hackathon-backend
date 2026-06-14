# 1. ビルド環境用コンテナ
FROM golang:1.22-alpine AS builder

WORKDIR /app

# 小文字のフォルダの中にある go.mod をコピーする
COPY hackathon-backend/go.mod ./
RUN go mod download

# すべてのファイルとフォルダ（main.goやhackathon-backendフォルダなど）をコピー
COPY . .

# 小文字のフォルダの外（今の場所）にある main.go をビルドする
RUN CGO_ENABLED=0 GOOS=linux go build -o main main.go

# 2. 実行環境用コンテナ
FROM alpine:3.19

WORKDIR /app

# ビルドしたバイナリファイルをコピー
COPY --from=builder /app/main .

EXPOSE 8080

CMD ["./main"]