"""
Database Module
Handles MongoDB connection using Motor (async MongoDB driver).
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Any, ClassVar, Optional

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Database:
    """
    Database connection manager.
    Provides a singleton-like pattern for MongoDB connection.
    """
    
    client: ClassVar[Optional[Any]] = None
    db: ClassVar[Optional[Any]] = None
    
    @classmethod
    async def connect(cls) -> None:
        """
        Establish connection to MongoDB.
        Should be called during application startup.
        """
        # Connection with timeout settings
        # srvServiceName default is "mongodb"; increase timeouts for slow DNS
        cls.client = AsyncIOMotorClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=30000,   # 30 seconds
            connectTimeoutMS=20000,           # 20 seconds
            socketTimeoutMS=20000,            # 20 seconds
        )
        cls.db = cls.client[settings.DATABASE_NAME]
        
        # Test connection
        try:
            await cls.client.admin.command("ping")
            logger.info("Connected to MongoDB: %s", settings.DATABASE_NAME)
        except Exception as e:
            logger.warning("MongoDB connection warning: %s", e)
            logger.info("The API will still start, but database operations will fail until MongoDB is available.")
            # Don't raise - allow app to start for development/testing
    
    @classmethod
    async def disconnect(cls) -> None:
        """
        Close MongoDB connection.
        Should be called during application shutdown.
        """
        if cls.client:
            cls.client.close()
            logger.info("Disconnected from MongoDB")
    
    @classmethod
    def get_database(cls) -> Any:
        """
        Get the database instance.
        
        Returns:
            AsyncIOMotorDatabase instance
            
        Raises:
            RuntimeError: If database is not connected
        """
        if cls.db is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return cls.db
    
    @classmethod
    def get_collection(cls, collection_name: str):
        """
        Get a specific collection from the database.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            AsyncIOMotorCollection instance
        """
        db = cls.get_database()
        return db[collection_name]


# Collection name constants
USERS_COLLECTION = "users"
PENDING_SIGNUPS_COLLECTION = "pending_signups"


async def get_users_collection():
    """
    Get the users collection.
    Convenience function for dependency injection.
    """
    return Database.get_collection(USERS_COLLECTION)
