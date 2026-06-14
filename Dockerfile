# 1. ビルド環境用コンテナ
FROM golang:1.22-alpine AS builder

WORKDIR /app

# go.mod だけを先にコピー（go.sumはコンテナ内で自動生成させるのでコピーしない）
COPY go.mod ./

# ソースコードをすべてコピー
COPY . .

# チェックサム検証をオフにし、コンテナ内で不足している依存関係を自動で整える魔法の2行
ENV GOSUMDB=off
RUN go mod tidy

# ビルドを実行してバイナリを作成
RUN CGO_ENABLED=0 GOOS=linux go build -o main .

# 2. 実行環境用コンテナ
FROM alpine:3.19

WORKDIR /app

# ビルドしたバイナリファイルをコピー
COPY --from=builder /app/main .

EXPOSE 8080

CMD ["./main"]