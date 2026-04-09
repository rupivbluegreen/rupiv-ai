# rupiv-go

Official Go SDK for the [Rupiv.ai](https://rupiv.ai) API.

## Installation

```bash
go get github.com/rupiv/rupiv-go
```

Requires Go 1.21 or later. No external dependencies.

## Quick Start

```go
package main

import (
	"context"
	"fmt"
	"log"

	rupiv "github.com/rupiv/rupiv-go"
)

func main() {
	client := rupiv.NewClient("your-api-key")

	// Track an event
	resp, err := client.TrackEvent(context.Background(), &rupiv.Event{
		CustomerID: "cust_123",
		EventType:  "feature_used",
		Properties: map[string]interface{}{
			"feature": "dashboard",
		},
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("Event tracked:", resp.ID)

	// Track an outcome
	outcome, err := client.TrackOutcome(context.Background(), &rupiv.Outcome{
		CustomerID:  "cust_123",
		OutcomeType: "purchase",
		Value:       249.99,
		Currency:    "USD",
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("Outcome tracked:", outcome.ID)

	// Get a customer
	cust, err := client.GetCustomer(context.Background(), "cust_123")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("Customer:", cust.Name)

	// List customers with pagination
	list, err := client.ListCustomers(context.Background(), &rupiv.ListOptions{
		Page:    1,
		PerPage: 25,
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("Found %d customers\n", list.TotalCount)

	// Create and accept a quote
	quote, err := client.CreateQuote(context.Background(), &rupiv.CreateQuoteRequest{
		CustomerID: "cust_123",
		LineItems: []rupiv.QuoteLineItem{
			{Description: "Pro Plan", Quantity: 1, UnitPrice: 99.00},
		},
		Currency: "USD",
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("Quote created:", quote.ID)

	accepted, err := client.AcceptQuote(context.Background(), quote.ID)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("Quote status:", accepted.Status)
}
```

## Configuration

```go
// Custom base URL (e.g., for staging)
client := rupiv.NewClient("your-api-key",
	rupiv.WithBaseURL("https://staging-api.rupiv.ai"),
)

// Custom HTTP client (e.g., for timeouts or proxies)
client := rupiv.NewClient("your-api-key",
	rupiv.WithHTTPClient(&http.Client{
		Timeout: 10 * time.Second,
	}),
)
```

## Error Handling

All methods return errors that can be inspected as `*rupiv.RupivError` for API-specific details:

```go
cust, err := client.GetCustomer(ctx, "cust_nonexistent")
if err != nil {
	if re, ok := rupiv.IsRupivError(err); ok {
		fmt.Println("Status:", re.StatusCode)   // e.g., 404
		fmt.Println("Message:", re.Message)      // e.g., "customer not found"
		fmt.Println("Request ID:", re.RequestID) // for support tickets
	} else {
		// Network error, timeout, etc.
		fmt.Println("Error:", err)
	}
}
```

## Idempotency

`TrackEvent` and `TrackOutcome` automatically generate a unique idempotency key (UUID v4) for each call. This prevents duplicate processing if a request is retried due to network issues.

## API Reference

| Method | Description |
|--------|-------------|
| `TrackEvent(ctx, *Event)` | Track a customer event |
| `TrackOutcome(ctx, *Outcome)` | Track a measurable outcome |
| `GetCustomer(ctx, id)` | Get a customer by ID |
| `ListCustomers(ctx, *ListOptions)` | List customers with pagination |
| `ListInvoices(ctx, *InvoiceListOptions)` | List invoices with filters |
| `CreateQuote(ctx, *CreateQuoteRequest)` | Create a pricing quote |
| `AcceptQuote(ctx, quoteID)` | Accept a quote |
| `RejectQuote(ctx, quoteID)` | Reject a quote |
