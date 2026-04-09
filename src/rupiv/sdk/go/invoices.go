package rupiv

import (
	"context"
	"net/url"
	"strconv"
)

// Invoice represents a Rupiv invoice.
type Invoice struct {
	ID         string  `json:"id"`
	CustomerID string  `json:"customer_id"`
	Amount     float64 `json:"amount"`
	Currency   string  `json:"currency"`
	Status     string  `json:"status"`
	DueDate    string  `json:"due_date,omitempty"`
	PaidAt     string  `json:"paid_at,omitempty"`
	CreatedAt  string  `json:"created_at,omitempty"`
}

// InvoiceListOptions extends ListOptions with invoice-specific filters.
type InvoiceListOptions struct {
	Page       int
	PerPage    int
	CustomerID string
	Status     string
}

// InvoiceListResponse is returned by ListInvoices.
type InvoiceListResponse struct {
	Invoices   []Invoice `json:"invoices"`
	TotalCount int       `json:"total_count"`
	Page       int       `json:"page"`
	PerPage    int       `json:"per_page"`
}

func (o *InvoiceListOptions) toQuery() url.Values {
	q := url.Values{}
	if o == nil {
		return q
	}
	if o.Page > 0 {
		q.Set("page", strconv.Itoa(o.Page))
	}
	if o.PerPage > 0 {
		q.Set("per_page", strconv.Itoa(o.PerPage))
	}
	if o.CustomerID != "" {
		q.Set("customer_id", o.CustomerID)
	}
	if o.Status != "" {
		q.Set("status", o.Status)
	}
	return q
}

// ListInvoices retrieves a paginated, optionally filtered list of invoices.
func (c *Client) ListInvoices(ctx context.Context, opts *InvoiceListOptions) (*InvoiceListResponse, error) {
	var resp InvoiceListResponse
	err := c.doRequest(ctx, "GET", "/v1/invoices", opts.toQuery(), nil, &resp, nil)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}
