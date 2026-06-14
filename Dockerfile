# 1. ビルド環境用コンテナ
FROM golang:1.22-alpine AS builder

WORKDIR /app

# さっき手動で作った go.mod をコピーする
COPY go.mod ./
RUN go mod download

# すべてのファイルをコピー
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