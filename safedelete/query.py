from typing import Optional, TypeVar, cast

from django.db.models import sql
from django.db.models.query_utils import Q
from django.db.models.sql.compiler import SQLCompiler

from .config import (
    DELETED_INVISIBLE,
    DELETED_ONLY_VISIBLE,
    DELETED_VISIBLE,
    DELETED_VISIBLE_BY_FIELD,
    FIELD_NAME,
)

_Q = TypeVar('_Q', bound='SafeDeleteQuery')


class SafeDeleteQuery(sql.Query):
    """Default query for the SafeDeleteQueryset.
    """

    _safedelete_filter_applied: bool = False
    _safedelete_force_visibility: Optional[int] = None
    _safedelete_visibility: int
    _safedelete_visibility_field: str

    def check_field_filter(self, **kwargs) -> None:
        """Check if the visibility for DELETED_VISIBLE_BY_FIELD needs to be put into effect.

        DELETED_VISIBLE_BY_FIELD is a temporary visibility flag that changes
        to DELETED_VISIBLE once asked for the named parameter defined in
        `_safedelete_force_visibility`. When evaluating the queryset, it will
        then filter on all models.
        """
        if self._safedelete_visibility == DELETED_VISIBLE_BY_FIELD \
                and self._safedelete_visibility_field in kwargs:
            self._safedelete_force_visibility = DELETED_VISIBLE

    def _filter_visibility(self) -> None:
        """Add deleted filters to the current QuerySet.

        Unlike QuerySet.filter, this does not return a clone.
        This is because QuerySet._fetch_all cannot work with a clone.
        """
        if not self.can_filter() or self._safedelete_filter_applied:
            return
        force_visibility = getattr(self, '_safedelete_force_visibility', None)
        visibility = force_visibility \
            if force_visibility is not None \
            else self._safedelete_visibility
        if visibility in (DELETED_INVISIBLE, DELETED_VISIBLE_BY_FIELD, DELETED_ONLY_VISIBLE):
            # Add a query manually, QuerySet.filter returns a clone.
            # QuerySet._fetch_all cannot work with clones.
            self.add_q(
                Q(
                    **{
                        FIELD_NAME + "__isnull": visibility
                        in (DELETED_INVISIBLE, DELETED_VISIBLE_BY_FIELD)
                    }
                )
            )
            self._safedelete_filter_applied = True

    def clone(self: _Q) -> _Q:
        clone = cast(_Q, super(SafeDeleteQuery, self).clone())
        clone._safedelete_visibility = self._safedelete_visibility
        clone._safedelete_visibility_field = self._safedelete_visibility_field
        clone._safedelete_filter_applied = self._safedelete_filter_applied
        if hasattr(self, '_safedelete_force_visibility'):
            clone._safedelete_force_visibility = self._safedelete_force_visibility
        return clone

    def get_compiler(self, *args, **kwargs) -> SQLCompiler:
        # Try to filter visibility at very end of the step
        self._filter_visibility()
        return super(SafeDeleteQuery, self).get_compiler(*args, **kwargs)

    def set_limits(self, low: Optional[int] = None, high: Optional[int] = None) -> None:
        # Filter visibility before query was sliced
        self._filter_visibility()
        return super(SafeDeleteQuery, self).set_limits(low, high)
