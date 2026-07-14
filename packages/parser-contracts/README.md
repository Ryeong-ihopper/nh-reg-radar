# Parser contracts

Versioned `normalized-document-v1` and parser/OCR adapter boundary shared by the backend
and worker. Provider SDK output never crosses this package: engines return a validated
`NormalizedDocument`, while raw payloads are retained through a restricted artifact store.
