"""What every `SnapshotStore` must do, whatever it stores blobs in.

The snapshot store is the evidence system of record: the bytes a card's quotation is checked
against. Three properties make one store interchangeable with another, and this contract is where
each is stated once rather than re-proved per adapter:

* **Content addressing.** A blob's key is the SHA-256 of its own bytes, so the same bytes always
  land under the same key and a second write of them is a no-op.
* **Immutability.** There is no overwrite and no delete in the port at all. A stored blob either
  comes back byte for byte or does not come back.
* **Detectable corruption.** A read whose bytes no longer hash to their key raises
  :class:`~debate_core.application.errors.BlobIntegrityError` rather than returning text a card
  would then be "verified" against (architecture proposal §8).

Corruption cannot be staged through the port, because no production path can rewrite a stored
blob. A binding therefore supplies the damage itself through the optional `corrupt_blob` fixture;
a binding that leaves it `None` skips that one test and keeps the rest.

Nothing here looks at a file path, a bucket name or a directory layout — where the bytes live is
the adapter's business and is tested in the adapter's own module.
"""

from __future__ import annotations

import hashlib

import pytest

from debate_core.application.errors import BlobIntegrityError, NotFound
from debate_core.application.ports import SnapshotStore
from debate_core.testing.contracts.harness import (
    AdapterContract,
    BlobCorruptor,
    SnapshotStoreFactory,
)

__all__ = ["SnapshotStoreContract"]

#: Two unrelated snapshot bodies. Real-looking rather than `b"a"`, so a failure message shows
#: which one came back.
ARCTIC_METHANE_HTML = b"<html><body><p>Arctic methane release is accelerating.</p></body></html>"
OCEAN_HEAT_HTML = b"<html><body><p>Ocean heat content reached a new high.</p></body></html>"

#: A key of the right shape that nothing was ever stored under.
UNWRITTEN_KEY = "f" * 64


class SnapshotStoreContract(AdapterContract):
    """Subclass this in a `Test…` class and override `make_adapter` to hold a store to the contract."""

    @pytest.fixture
    def make_adapter(self) -> SnapshotStoreFactory:
        """Return a factory handing out handles onto one empty blob store.

        A binding must override this. See `README.md` in this directory.
        """
        raise NotImplementedError(
            "a SnapshotStoreContract binding must override the `make_adapter` fixture with "
            "a factory returning handles onto one empty blob store"
        )

    @pytest.fixture
    def store(self, make_adapter: SnapshotStoreFactory) -> SnapshotStore:
        """The store under test; the contract's tests use this rather than the factory."""
        return make_adapter()

    @pytest.fixture
    def corrupt_blob(self) -> BlobCorruptor | None:
        """Damage a stored blob without changing its key, or `None` if this store cannot stage it.

        Overriding it turns on `test_a_blob_whose_bytes_no_longer_match_its_key_is_refused`, which
        is the one property of this port that cannot be exercised through the port itself.
        """
        return None

    # ----------------------------------------------------------------------------------------
    # Content addressing
    # ----------------------------------------------------------------------------------------

    async def test_put_returns_the_sha256_of_the_bytes_stored(self, store: SnapshotStore) -> None:
        """The key is the digest and nothing else, so two stores agree on it without talking."""
        key = await store.put(ARCTIC_METHANE_HTML)

        assert key == hashlib.sha256(ARCTIC_METHANE_HTML).hexdigest()

    async def test_get_returns_exactly_the_bytes_that_were_put(self, store: SnapshotStore) -> None:
        """Byte for byte: a snapshot that came back re-encoded would fail re-verification later."""
        key = await store.put(ARCTIC_METHANE_HTML)

        assert await store.get(key) == ARCTIC_METHANE_HTML

    async def test_different_bytes_are_stored_under_different_keys(self, store: SnapshotStore) -> None:
        arctic_key = await store.put(ARCTIC_METHANE_HTML)
        ocean_key = await store.put(OCEAN_HEAT_HTML)

        assert arctic_key != ocean_key
        assert await store.get(arctic_key) == ARCTIC_METHANE_HTML
        assert await store.get(ocean_key) == OCEAN_HEAT_HTML

    async def test_empty_bytes_round_trip(self, store: SnapshotStore) -> None:
        """A zero-length body is a legitimate retrieval — a blocked page, a stripped PDF — not an error."""
        key = await store.put(b"")

        assert key == hashlib.sha256(b"").hexdigest()
        assert await store.get(key) == b""
        assert await store.exists(key) is True

    async def test_a_byte_of_difference_produces_a_different_key(self, store: SnapshotStore) -> None:
        """The property the whole platform leans on: altered text cannot pass as the stored text."""
        original_key = await store.put(ARCTIC_METHANE_HTML)
        altered_key = await store.put(ARCTIC_METHANE_HTML.replace(b"accelerating", b"decelerating"))

        assert original_key != altered_key
        assert await store.get(original_key) == ARCTIC_METHANE_HTML

    # ----------------------------------------------------------------------------------------
    # Idempotence and immutability
    # ----------------------------------------------------------------------------------------

    async def test_putting_identical_bytes_twice_stores_one_blob(self, store: SnapshotStore) -> None:
        """Storing the same source twice is one blob, so a re-fetch costs nothing and changes nothing."""
        first_key = await store.put(ARCTIC_METHANE_HTML)
        second_key = await store.put(ARCTIC_METHANE_HTML)

        assert first_key == second_key
        assert await store.get(first_key) == ARCTIC_METHANE_HTML

    async def test_a_repeat_put_cannot_disturb_other_blobs(self, store: SnapshotStore) -> None:
        arctic_key = await store.put(ARCTIC_METHANE_HTML)
        ocean_key = await store.put(OCEAN_HEAT_HTML)

        await store.put(ARCTIC_METHANE_HTML)

        assert await store.get(arctic_key) == ARCTIC_METHANE_HTML
        assert await store.get(ocean_key) == OCEAN_HEAT_HTML

    async def test_a_second_handle_reads_what_the_first_stored(
        self, store: SnapshotStore, make_adapter: SnapshotStoreFactory
    ) -> None:
        """Two handles are two views of one store, not two stores; the later contracts rely on it."""
        key = await store.put(ARCTIC_METHANE_HTML)

        assert await make_adapter().get(key) == ARCTIC_METHANE_HTML

    # ----------------------------------------------------------------------------------------
    # Absence and damage
    # ----------------------------------------------------------------------------------------

    async def test_exists_is_false_before_a_put_and_true_after(self, store: SnapshotStore) -> None:
        key = hashlib.sha256(ARCTIC_METHANE_HTML).hexdigest()

        assert await store.exists(key) is False
        await store.put(ARCTIC_METHANE_HTML)
        assert await store.exists(key) is True

    async def test_exists_is_false_for_a_key_nothing_was_stored_under(self, store: SnapshotStore) -> None:
        await store.put(ARCTIC_METHANE_HTML)

        assert await store.exists(UNWRITTEN_KEY) is False

    async def test_getting_a_key_nothing_was_stored_under_raises_not_found(
        self, store: SnapshotStore
    ) -> None:
        with pytest.raises(NotFound) as refused:
            await store.get(UNWRITTEN_KEY)

        assert refused.value.key == UNWRITTEN_KEY

    async def test_a_blob_whose_bytes_no_longer_match_its_key_is_refused(
        self, store: SnapshotStore, corrupt_blob: BlobCorruptor | None
    ) -> None:
        """Damaged evidence fails loudly. It is never repaired, and it is never served anyway."""
        if corrupt_blob is None:
            pytest.skip("this binding supplies no way to damage a stored blob")
        key = await store.put(ARCTIC_METHANE_HTML)

        corrupt_blob(key, OCEAN_HEAT_HTML)

        with pytest.raises(BlobIntegrityError) as refused:
            await store.get(key)
        assert refused.value.key == key
