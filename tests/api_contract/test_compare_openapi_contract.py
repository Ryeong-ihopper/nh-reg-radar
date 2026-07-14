import unittest
from typing import final, override

from scripts.compare_openapi_contract import JsonObject, compare_contracts


def make_contract(
    *,
    path: str = "/things",
    status: str = "200",
    id_type: str = "string",
    operation_id: str = "listThings",
    request_type: str = "string",
    path_parameter: str = "tenantId",
    security_scheme: str = "BearerAuth",
) -> JsonObject:
    return {
        "security": [{security_scheme: []}],
        "paths": {
            path: {
                "parameters": [
                    {
                        "name": path_parameter,
                        "in": "header",
                        "schema": {"type": "string"},
                    }
                ],
                "get": {
                    "operationId": operation_id,
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"type": request_type}}
                        }
                    },
                    "responses": {
                        status: {"$ref": "#/components/responses/ThingResponse"}
                    },
                },
            }
        },
        "components": {
            "schemas": {
                "Thing": {
                    "type": "object",
                    "properties": {"id": {"type": id_type}},
                }
            },
            "responses": {
                "ThingResponse": {
                    "description": "OK",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Thing"}
                        }
                    },
                }
            },
            "securitySchemes": {security_scheme: {"type": "http", "scheme": "bearer"}},
        },
    }


@final
class OpenApiContractComparisonTest(unittest.TestCase):
    contract: JsonObject = {}

    @override
    def setUp(self) -> None:
        self.contract = make_contract()

    def assert_drift(self, generated: JsonObject) -> None:
        self.assertTrue(compare_contracts(self.contract, generated))

    def test_equivalent_contract_ignores_non_contract_metadata(self) -> None:
        generated = make_contract()
        generated["info"] = {"title": "Generated", "version": "different"}
        self.assertEqual([], compare_contracts(self.contract, generated))

    def test_path_and_method_drift_is_detected(self) -> None:
        self.assert_drift(make_contract(path="/other"))

    def test_schema_drift_is_detected(self) -> None:
        self.assert_drift(make_contract(id_type="integer"))

    def test_status_drift_is_detected(self) -> None:
        self.assert_drift(make_contract(status="201"))

    def test_operation_and_request_drift_is_detected(self) -> None:
        self.assert_drift(make_contract(operation_id="readThings"))
        self.assert_drift(make_contract(request_type="integer"))

    def test_path_parameter_drift_is_detected(self) -> None:
        self.assert_drift(make_contract(path_parameter="departmentId"))

    def test_root_security_and_component_drift_is_detected(self) -> None:
        self.assert_drift(make_contract(security_scheme="SessionAuth"))


if __name__ == "__main__":
    _ = unittest.main()
