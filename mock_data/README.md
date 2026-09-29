# mock_data/

Canonical mock government-portal records live in `backend/app/adapters/mock_data/*.json`
(the adapters load them from there). This directory exists as the documented drop-point
for the source JSONs used to generate/refresh those adapter fixtures.

All records are **fictional demo data** — clearly labeled `is_mock: true` everywhere
they are served. Nothing here represents live government data.
