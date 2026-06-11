package model

type Item struct {
    ID          int    `json:"id"`
    Title       string `json:"title"`
    Description string `json:"description"`
    Price       int    `json:"price"`
}
