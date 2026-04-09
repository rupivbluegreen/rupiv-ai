package rupiv

import (
	"context"
	"fmt"
)

// QuoteLineItem represents a single line on a quote.
type QuoteLineItem struct {
	Description string  `json:"description"`
	Quantity    int     `json:"quantity"`
	UnitPrice   float64 `json:"unit_price"`
	Amount      float64 `json:"amount,omitempty"`
}

// Quote represents a Rupiv pricing quote.
type Quote struct {
	ID         string          `json:"id,omitempty"`
	CustomerID string          `json:"customer_id"`
	LineItems  []QuoteLineItem `json:"line_items"`
	Currency   string          `json:"currency,omitempty"`
	Total      float64         `json:"total,omitempty"`
	Status     string          `json:"status,omitempty"`
	ExpiresAt  string          `json:"expires_at,omitempty"`
	CreatedAt  string          `json:"created_at,omitempty"`
}

// CreateQuoteRequest is the payload for creating a new quote.
type CreateQuoteRequest struct {
	CustomerID string          `json:"customer_id"`
	LineItems  []QuoteLineItem `json:"line_items"`
	Currency   string          `json:"currency,omitempty"`
	ExpiresAt  string          `json:"expires_at,omitempty"`
}

// CreateQuote creates a new pricing quote.
func (c *Client) CreateQuote(ctx context.Context, req *CreateQuoteRequest) (*Quote, error) {
	var quote Quote
	err := c.doRequest(ctx, "POST", "/v1/quotes", nil, req, &quote, nil)
	if err != nil {
		return nil, err
	}
	return &quote, nil
}

// AcceptQuote marks a quote as accepted.
func (c *Client) AcceptQuote(ctx context.Context, quoteID string) (*Quote, error) {
	var quote Quote
	err := c.doRequest(ctx, "POST", fmt.Sprintf("/v1/quotes/%s/accept", quoteID), nil, nil, &quote, nil)
	if err != nil {
		return nil, err
	}
	return &quote, nil
}

// RejectQuote marks a quote as rejected.
func (c *Client) RejectQuote(ctx context.Context, quoteID string) (*Quote, error) {
	var quote Quote
	err := c.doRequest(ctx, "POST", fmt.Sprintf("/v1/quotes/%s/reject", quoteID), nil, nil, &quote, nil)
	if err != nil {
		return nil, err
	}
	return &quote, nil
}
