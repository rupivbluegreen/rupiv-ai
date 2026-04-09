package rupiv

import (
	"context"
	"time"
)

// Event represents a trackable event in the Rupiv system.
type Event struct {
	CustomerID string                 `json:"customer_id"`
	EventType  string                 `json:"event_type"`
	Properties map[string]interface{} `json:"properties,omitempty"`
	Timestamp  *time.Time             `json:"timestamp,omitempty"`
}

// Outcome represents a measurable outcome tied to a customer action.
type Outcome struct {
	CustomerID  string                 `json:"customer_id"`
	OutcomeType string                 `json:"outcome_type"`
	Value       float64                `json:"value,omitempty"`
	Currency    string                 `json:"currency,omitempty"`
	Properties  map[string]interface{} `json:"properties,omitempty"`
	Timestamp   *time.Time             `json:"timestamp,omitempty"`
}

// EventResponse is returned after successfully tracking an event or outcome.
type EventResponse struct {
	ID             string `json:"id"`
	IdempotencyKey string `json:"idempotency_key"`
	Status         string `json:"status"`
}

// TrackEvent sends an event to the Rupiv API. An idempotency key is
// automatically generated for each call to prevent duplicate processing.
func (c *Client) TrackEvent(ctx context.Context, event *Event) (*EventResponse, error) {
	var resp EventResponse
	headers := map[string]string{
		"Idempotency-Key": newUUID(),
	}
	err := c.doRequest(ctx, "POST", "/v1/events", nil, event, &resp, headers)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}

// TrackOutcome sends an outcome to the Rupiv API. An idempotency key is
// automatically generated for each call to prevent duplicate processing.
func (c *Client) TrackOutcome(ctx context.Context, outcome *Outcome) (*EventResponse, error) {
	var resp EventResponse
	headers := map[string]string{
		"Idempotency-Key": newUUID(),
	}
	err := c.doRequest(ctx, "POST", "/v1/events/outcomes", nil, outcome, &resp, headers)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}
