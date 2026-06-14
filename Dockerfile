# 1. ビルド環境用コンテナ
FROM golang:1.22-alpine AS builder

WORKDIR /app

# 一番外側にある go.mod と go.sum をコピー
COPY go.mod go.sum ./
RUN go mod download

# すべてのソースコード（小文字のフォルダやmain.goなど）をコピー
COPY . .

# ビルドを実行してバイナリを作成
RUN CGO_ENABLED=0 GOOS=linux go build -o main .

# 2. 実行環境用コンテナ
FROM alpine:3.19

WORKDIR /app

# ビルドしたバイナリファイルをコピー
COPY --from=builder /app/main .

EXPOSE 8080

CMD ["./main"]