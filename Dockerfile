# 1. ビルド環境用コンテナ
FROM golang:1.22-alpine AS builder

WORKDIR /app

# 依存関係のキャッシュを利用するため、先にgo.modとgo.sumをコピー
COPY go.mod go.sum ./
RUN go mod download

# ソースコードをすべてコピーしてビルド
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o main .

# 2. 実行環境用コンテナ
FROM alpine:3.19

WORKDIR /app

# ビルドしたバイナリファイルをコピー
COPY --from=builder /app/main .

EXPOSE 8080

CMD ["./main"]