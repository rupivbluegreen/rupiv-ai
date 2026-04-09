package rupiv

import (
	"errors"
	"fmt"
)

// RupivError represents an error response from the Rupiv API.
type RupivError struct {
	// StatusCode is the HTTP status code returned by the API.
	StatusCode int `json:"status_code"`
	// Message is the human-readable error message.
	Message string `json:"message"`
	// RequestID is the unique identifier for the request, useful for support.
	RequestID string `json:"request_id"`
}

// Error implements the error interface.
func (e *RupivError) Error() string {
	if e.RequestID != "" {
		return fmt.Sprintf("rupiv: %d %s (request_id: %s)", e.StatusCode, e.Message, e.RequestID)
	}
	return fmt.Sprintf("rupiv: %d %s", e.StatusCode, e.Message)
}

// IsRupivError checks whether err is a *RupivError and returns it if so.
func IsRupivError(err error) (*RupivError, bool) {
	var re *RupivError
	if errors.As(err, &re) {
		return re, true
	}
	return nil, false
}
