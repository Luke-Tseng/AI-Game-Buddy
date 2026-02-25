import logging
from typing import Any

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient

from app.config import settings

logger = logging.getLogger(__name__)


class BlobService:
    def __init__(self):
        self.client: BlobServiceClient
        if settings.BLOB_ENDPOINT:
            logger.info("Initializing Blob Service Client with Azure Credentials")
            credential = DefaultAzureCredential()
            self.client = BlobServiceClient(
                account_url=settings.BLOB_ENDPOINT, credential=credential
            )
        else:
            raise ValueError(
                "Storage configuration missing. Set BLOB_ENDPOINT"
            )

        if not self.client:
            raise ConnectionError("Failed to connect to BlobServiceClient")

    async def close(self):
        logger.info("Closing Blob Storage client session")
        await self.client.close()

    async def write_blob(self, container_name: str, filename: str, blobstream: Any):
        if not container_name:
            raise ValueError("Container name cannot be empty")
        if not filename:
            raise ValueError("Filename cannot be empty")
        if not blobstream:
            raise ValueError("Blob content cannot be null")
        try:
            container_client = self.client.get_container_client(container_name)
            # Check if container exists
            try:
                await container_client.get_container_properties()
            except ResourceNotFoundError:
                await container_client.create_container()
                logger.info(f"Container '{container_name}' created.")

            blob_client = container_client.get_blob_client(filename)
            await blob_client.upload_blob(blobstream, overwrite=True)
            logger.info(
                f"Blob '{filename}' uploaded successfully to container '{container_name}'"
            )

        except HttpResponseError as e:
            logger.error(f"Azure Storage request failed: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during blob upload: {e}")
            raise

    async def get_blob(self, container_name: str, filename: str) -> bytes:
        if not container_name:
            raise ValueError("Container name cannot be empty")
        if not filename:
            raise ValueError("Filename cannot be empty")
        try:
            container_client = self.client.get_container_client(container_name)
            blob_client = container_client.get_blob_client(filename)
            stream = await blob_client.download_blob()
            data = await stream.readall()
            logger.info(
                f"Blob '{filename}' retrieved from container '{container_name}'"
            )
            return data
        except ResourceNotFoundError:
            logger.error(f"Blob '{filename}' not found in container '{container_name}'")
            raise
        except HttpResponseError as e:
            logger.error(f"Azure Storage request failed: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during blob retrieval: {e}")
            raise

    async def delete_blob(self, container_name: str, filename: str):
        if not container_name:
            raise ValueError("Container name cannot be empty")
        if not filename:
            raise ValueError("Filename cannot be empty")
        try:
            container_client = self.client.get_container_client(container_name)
            blob_client = container_client.get_blob_client(filename)
            await blob_client.delete_blob()
            logger.info(f"Blob '{filename}' deleted from container '{container_name}'")
        except ResourceNotFoundError:
            logger.warning(
                f"Attempted to delete blob '{filename}', but does not exist in container {container_name}"
            )
        except HttpResponseError as e:
            logger.error(f"Azure Storage request failed: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during blob deletion: {e}")
            raise
