"""Model routing: the policy that decides which model answers each task class.

:class:`~debate_core.integrations.models.routing_policy.RoutingPolicy` reads a
`config/model_routing.*.yaml` file and resolves a call into the route it takes
(v1-e05-t01-model-router-port). The offline routers that serve recorded answers arrive here with
v1-e05-t03-fake-replay-models; the Bedrock adapter has its own subpackage, because nothing in this
one may depend on the AWS SDK.
"""

from debate_core.integrations.models.routing_policy import ROUTING_SCHEMA_VERSION, ModelRoute, RoutingPolicy

__all__ = ["ROUTING_SCHEMA_VERSION", "ModelRoute", "RoutingPolicy"]
