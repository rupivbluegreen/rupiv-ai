package rupiv

import (
	"context"
	"fmt"
	"net/url"
	"strconv"
)

// Customer represents a Rupiv customer record.
type Customer struct {
	ID        string                 `json:"id"`
	Name      string                 `json:"name"`
	Email     string                 `json:"email"`
	Plan      string                 `json:"plan,omitempty"`
	Status    string                 `json:"status,omitempty"`
	Metadata  map[string]interface{} `json:"metadata,omitempty"`
	CreatedAt string                 `json:"created_at,omitempty"`
	UpdatedAt string                 `json:"updated_at,omitempty"`
}

// ListOptions controls pagination for list endpoints.
type ListOptions struct {
	// Page number, starting at 1.
	Page int
	// PerPage is the number of items per page (max 100).
	PerPage int
}

// CustomerListResponse is returned by ListCustomers.
type CustomerListResponse struct {
	Customers  []Customer `json:"customers"`
	TotalCount int        `json:"total_count"`
	Page       int        `json:"page"`
	PerPage    int        `json:"per_page"`
}

func (o *ListOptions) toQuery() url.Values {
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
	return q
}

// GetCustomer retrieves a single customer by ID.
func (c *Client) GetCustomer(ctx context.Context, customerID string) (*Customer, error) {
	var cust Customer
	err := c.doRequest(ctx, "GET", fmt.Sprintf("/v1/customers/%s", customerID), nil, nil, &cust, nil)
	if err != nil {
		return nil, err
	}
	return &cust, nil
}

// ListCustomers retrieves a paginated list of customers.
func (c *Client) ListCustomers(ctx context.Context, opts *ListOptions) (*CustomerListResponse, error) {
	var resp CustomerListResponse
	err := c.doRequest(ctx, "GET", "/v1/customers", opts.toQuery(), nil, &resp, nil)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}
