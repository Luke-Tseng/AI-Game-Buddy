import logging
from typing import Any

from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


class CosmosService:
    def __init__(self):
        self.client: CosmosClient | None = None

        if settings.COSMOS_ENDPOINT:
            # Use managed identity
            logger.info("Initializing Cosmos Service Client with Azure Credentials")
            credential = DefaultAzureCredential()
            self.client = CosmosClient(
                url=settings.COSMOS_ENDPOINT, credential=credential
            )
        else:
            raise ValueError("Database configuration missing. Set COSMOS_ENDPOINT")

        if not self.client:
            raise ConnectionError("Failed to connect to CosmosClient")

        db_client = self.client.get_database_client(settings.COSMOS_DATABASE_NAME)
        self.users_container_client = db_client.get_container_client("users")
        self.rooms_container_client = db_client.get_container_client("rooms")
        self.chats_container_client = db_client.get_container_client("chats")

    async def close(self):
        logger.info("Closing Cosmos client session")
        await self.client.close()

    def get_container(self, container_type: str):
        if container_type == "users":
            return self.users_container_client
        elif container_type == "rooms":
            return self.rooms_container_client
        elif container_type == "chats":
            return self.chats_container_client
        else:
            raise ValueError(f"Container type '{container_type}' does not exist")

    # Database access functions
    async def add_item(self, item: dict[str, Any], container_type: str):
        if not item:
            raise ValueError("Invalid Item")

        container = self.get_container(container_type)
        logger.info(f"Adding item to container '{container.id}': '{item.get('id')}'")
        try:
            await container.create_item(body=item)
        except CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB error adding item '{item.get('id')}': {e.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred during the patch operation",
            ) from e
        except Exception as e:
            logger.error(
                f"Failed to add item '{item.get('id')}' to '{container.id}': {e}"
            )
            raise

    async def get_item(self, item_id: str, partition_key: str, container_type: str):
        if not item_id or not partition_key:
            raise ValueError("Item ID and partition key cannot be empty")

        container = self.get_container(container_type)
        logger.info(
            f"Geting item from container '{container.id}' with item id '{item_id}' and partition key '{partition_key}'"
        )
        try:
            item = await container.read_item(item=item_id, partition_key=partition_key)
            return item
        except CosmosResourceNotFoundError:
            logger.warning(
                f"Item '{item_id}' with partition key '{partition_key}' not found in container '{container.id}'"
            )
            return None
        except CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB error getting item '{item_id}': {e.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred during the get operation",
            ) from e
        except Exception as e:
            logger.error(
                f"Failed to get item '{item_id}' with partition key '{partition_key}' from '{container.id}': {e}"
            )
            raise

    # Getting items using a SQL Query
    async def get_items_by_query(
        self,
        query: str,
        container_type: str,
        parameters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if not query:
            raise ValueError("Query string cannot be empty")

        container = self.get_container(container_type)
        logger.info(f"Querying items in container '{container.id}': {query}")
        try:
            items = [
                item
                async for item in container.query_items(
                    query=query, parameters=parameters, enable_scan_in_query=True
                )
            ]
            logger.info(f"Query returned {len(items)} items")
            return items
        except CosmosHttpResponseError as e:
            logger.error(
                f"Cosmos DB query failed with status {e.status_code}: {e.message}"
            )
            if e.status_code == 400:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid query syntax: {e.message}",
                ) from e
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"A database error occurred while executing the query: {query}",
                ) from e
        except Exception as e:
            logger.error(f"Failed to execute query {query}: {e}")
            raise

    async def update_item(self, item: dict[str, Any], container_type: str):
        if not item:
            raise ValueError("Invalid Item")

        container = self.get_container(container_type)
        logger.info(f"Updating item to container '{container.id}': '{item.get('id')}'")
        try:
            await container.upsert_item(body=item)
        except CosmosResourceNotFoundError as e:
            logger.warning(
                f"Item '{item.get('id')}' not found in container '{container.id}' for patching"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Item with id '{item.get('id')}' not found",
            ) from e
        except CosmosHttpResponseError as e:
            logger.error(
                f"Cosmos DB error updating item '{item.get('id')}': {e.message}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred during the patch operation",
            ) from e
        except Exception as e:
            logger.error(
                f"Failed to update item '{item.get('id')}' to '{container.id}': {e}"
            )
            raise

    async def patch_item(
        self,
        item_id: str,
        partition_key: str,
        patch_operations: dict[str, Any],
        container_type: str,
    ):
        if not item_id or not partition_key:
            raise ValueError("Item ID and partition key cannot be empty")

        container = self.get_container(container_type)
        logger.info(f"Patching item '{item_id}' from container '{container.id}")
        try:
            await container.patch_item(
                item=item_id,
                partition_key=partition_key,
                patch_operations=patch_operations,
            )
        except CosmosResourceNotFoundError as e:
            logger.warning(
                f"Item '{item_id}' not found in container '{container.id}' for patching"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Item with id '{item_id}' not found",
            ) from e
        except CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB error patching item '{item_id}': {e.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred during the patch operation",
            ) from e
        except Exception as e:
            logger.critical(
                f"An unexpected error occurred while patching item '{item_id}': {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected internal error occurred",
            ) from e

    async def delete_item(self, item_id: str, partition_key: str, container_type: str):
        if not item_id or not partition_key:
            raise ValueError("Item ID and partition key cannot be empty")

        container = self.get_container(container_type)
        logger.info(
            f"Deleting item from container '{container.id}': '{item_id}' with partition key '{partition_key}'"
        )
        try:
            await container.delete_item(item=item_id, partition_key=partition_key)
        except CosmosResourceNotFoundError as e:
            logger.warning(
                f"Item '{item_id}' not found in container '{container.id}' for deleting"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Item with id '{item_id}' not found",
            ) from e
        except CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB error deleting item '{item_id}': {e.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred during the delete operation",
            ) from e
        except Exception as e:
            logger.critical(
                f"An unexpected error occurred while patching item '{item_id}': {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected internal error occurred",
            ) from e
