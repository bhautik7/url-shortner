"""
Unit Tests for Redis Counter Service and Batch Range Allocation.
"""

from unittest.mock import AsyncMock
import pytest
from services.write_service.app.services.counter_service import CounterService
from shared.utilities.errors import DependencyUnavailableError


@pytest.mark.asyncio
async def test_counter_service_batch_allocation():
    """
    Test that CounterService leases a batch of IDs via Redis INCRBY
    and dispenses them monotonically in-memory.
    """
    mock_redis = AsyncMock()
    # First INCRBY returns 1000000 + 5 = 1000005 (batch size 5)
    mock_redis.incrby.return_value = 1000005
    mock_redis.set.return_value = True

    service = CounterService(
        redis_client=mock_redis,
        counter_key="test_counter",
        batch_size=5,
        start_offset=1000000,
    )

    # Dispense first 5 IDs
    ids = [await service.get_next_id() for _ in range(5)]
    assert ids == [1000001, 1000002, 1000003, 1000004, 1000005]
    # Redis INCRBY should have been called only once for the first 5 IDs
    assert mock_redis.incrby.call_count == 1

    # 6th call should trigger a new batch lease from Redis
    mock_redis.incrby.return_value = 1000010
    next_id = await service.get_next_id()
    assert next_id == 1000006
    assert mock_redis.incrby.call_count == 2


@pytest.mark.asyncio
async def test_counter_service_redis_failure_raises_dependency_error():
    """
    Test that Redis failure during batch leasing raises DependencyUnavailableError.
    """
    mock_redis = AsyncMock()
    mock_redis.set.side_effect = Exception("Redis connection refused")

    service = CounterService(
        redis_client=mock_redis,
        counter_key="test_counter",
        batch_size=1000,
        start_offset=1000000,
    )

    with pytest.raises(DependencyUnavailableError):
        await service.get_next_id()
