package rupiv

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func testClient(t *testing.T, handler http.HandlerFunc) (*Client, *httptest.Server) {
	t.Helper()
	srv := httptest.NewServer(handler)
	c := NewClient("test-api-key", WithBaseURL(srv.URL))
	return c, srv
}

func TestTrackEvent(t *testing.T) {
	c, srv := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		if r.URL.Path != "/v1/events" {
			t.Errorf("expected /v1/events, got %s", r.URL.Path)
		}
		if r.Header.Get("X-API-Key") != "test-api-key" {
			t.Errorf("expected X-API-Key header to be test-api-key, got %s", r.Header.Get("X-API-Key"))
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("expected Content-Type application/json, got %s", r.Header.Get("Content-Type"))
		}

		var event Event
		if err := json.NewDecoder(r.Body).Decode(&event); err != nil {
			t.Fatalf("failed to decode request body: %v", err)
		}
		if event.CustomerID != "cust_123" {
			t.Errorf("expected customer_id cust_123, got %s", event.CustomerID)
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(EventResponse{
			ID:             "evt_abc",
			IdempotencyKey: "key_xyz",
			Status:         "accepted",
		})
	})
	defer srv.Close()

	resp, err := c.TrackEvent(context.Background(), &Event{
		CustomerID: "cust_123",
		EventType:  "page_view",
		Properties: map[string]interface{}{"page": "/home"},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.ID != "evt_abc" {
		t.Errorf("expected id evt_abc, got %s", resp.ID)
	}
	if resp.Status != "accepted" {
		t.Errorf("expected status accepted, got %s", resp.Status)
	}
}

func TestTrackOutcome(t *testing.T) {
	c, srv := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/events/outcomes" {
			t.Errorf("expected /v1/events/outcomes, got %s", r.URL.Path)
		}

		var outcome Outcome
		if err := json.NewDecoder(r.Body).Decode(&outcome); err != nil {
			t.Fatalf("failed to decode request body: %v", err)
		}
		if outcome.Value != 99.99 {
			t.Errorf("expected value 99.99, got %f", outcome.Value)
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(EventResponse{
			ID:     "out_def",
			Status: "accepted",
		})
	})
	defer srv.Close()

	resp, err := c.TrackOutcome(context.Background(), &Outcome{
		CustomerID:  "cust_123",
		OutcomeType: "purchase",
		Value:       99.99,
		Currency:    "USD",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.ID != "out_def" {
		t.Errorf("expected id out_def, got %s", resp.ID)
	}
}

func TestAutoIdempotencyKey(t *testing.T) {
	keys := make(map[string]bool)
	c, srv := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		key := r.Header.Get("Idempotency-Key")
		if key == "" {
			t.Error("expected Idempotency-Key header to be set")
		}
		if keys[key] {
			t.Error("duplicate idempotency key detected")
		}
		keys[key] = true

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(EventResponse{ID: "evt_1", Status: "accepted"})
	})
	defer srv.Close()

	for i := 0; i < 5; i++ {
		_, err := c.TrackEvent(context.Background(), &Event{
			CustomerID: "cust_123",
			EventType:  "click",
		})
		if err != nil {
			t.Fatalf("unexpected error on call %d: %v", i, err)
		}
	}

	if len(keys) != 5 {
		t.Errorf("expected 5 unique keys, got %d", len(keys))
	}
}

func TestErrorHandling(t *testing.T) {
	c, srv := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Request-Id", "req_err_001")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnprocessableEntity)
		json.NewEncoder(w).Encode(map[string]string{
			"message": "customer_id is required",
		})
	})
	defer srv.Close()

	_, err := c.TrackEvent(context.Background(), &Event{})
	if err == nil {
		t.Fatal("expected error, got nil")
	}

	re, ok := IsRupivError(err)
	if !ok {
		t.Fatalf("expected RupivError, got %T", err)
	}
	if re.StatusCode != 422 {
		t.Errorf("expected status 422, got %d", re.StatusCode)
	}
	if re.Message != "customer_id is required" {
		t.Errorf("expected message 'customer_id is required', got %s", re.Message)
	}
	if re.RequestID != "req_err_001" {
		t.Errorf("expected request_id req_err_001, got %s", re.RequestID)
	}
}

func TestGetCustomer(t *testing.T) {
	c, srv := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("expected GET, got %s", r.Method)
		}
		if r.URL.Path != "/v1/customers/cust_456" {
			t.Errorf("expected /v1/customers/cust_456, got %s", r.URL.Path)
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(Customer{
			ID:    "cust_456",
			Name:  "Acme Corp",
			Email: "billing@acme.com",
			Plan:  "enterprise",
		})
	})
	defer srv.Close()

	cust, err := c.GetCustomer(context.Background(), "cust_456")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cust.ID != "cust_456" {
		t.Errorf("expected id cust_456, got %s", cust.ID)
	}
	if cust.Name != "Acme Corp" {
		t.Errorf("expected name Acme Corp, got %s", cust.Name)
	}
	if cust.Plan != "enterprise" {
		t.Errorf("expected plan enterprise, got %s", cust.Plan)
	}
}
