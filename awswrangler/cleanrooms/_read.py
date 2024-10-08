"""Amazon Clean Rooms Module hosting read_* functions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Iterator

import boto3

import awswrangler.pandas as pd
from awswrangler import _utils, exceptions, s3
from awswrangler._sql_formatter import _process_sql_params
from awswrangler.cleanrooms._utils import wait_query

if TYPE_CHECKING:
    from mypy_boto3_cleanrooms.type_defs import ProtectedQuerySQLParametersTypeDef

_logger: logging.Logger = logging.getLogger(__name__)


def _delete_after_iterate(
    dfs: Iterator[pd.DataFrame], keep_files: bool, kwargs: dict[str, Any]
) -> Iterator[pd.DataFrame]:
    yield from dfs
    if keep_files is False:
        s3.delete_objects(**kwargs)


def read_sql_query(
    sql: str | None = None,
    analysis_template_arn: str | None = None,
    membership_id: str = "",
    output_bucket: str = "",
    output_prefix: str = "",
    keep_files: bool = True,
    params: dict[str, Any] | None = None,
    chunksize: int | bool | None = None,
    use_threads: bool | int = True,
    boto3_session: boto3.Session | None = None,
    pyarrow_additional_kwargs: dict[str, Any] | None = None,
) -> Iterator[pd.DataFrame] | pd.DataFrame:
    """Execute Clean Rooms Protected SQL query and return the results as a Pandas DataFrame.

    Note
    ----
    One of `sql` or `analysis_template_arn` must be supplied, not both.

    Parameters
    ----------
    sql
        SQL query
    analysis_template_arn
        ARN of the analysis template
    membership_id
        Membership ID
    output_bucket
        S3 output bucket name
    output_prefix
        S3 output prefix
    keep_files
        Whether files in S3 output bucket/prefix are retained. 'True' by default
    params
        (Client-side) If used in combination with the `sql` parameter, it's the Dict of parameters used
        for constructing the SQL query. Only named parameters are supported.
        The dict must be in the form {'name': 'value'} and the SQL query must contain
        `:name`. Note that for varchar columns and similar, you must surround the value in single quotes.

        (Server-side) If used in combination with the `analysis_template_arn` parameter, it's the Dict of parameters
        supplied with the analysis template. It must be a string to string dict in the form {'name': 'value'}.
    chunksize
        If passed, the data is split into an iterable of DataFrames (Memory friendly).
        If `True` an iterable of DataFrames is returned without guarantee of chunksize.
        If an `INTEGER` is passed, an iterable of DataFrames is returned with maximum rows
        equal to the received INTEGER
    use_threads
        True to enable concurrent requests, False to disable multiple threads.
        If enabled os.cpu_count() is used as the maximum number of threads.
        If integer is provided, specified number is used
    boto3_session
        The default boto3 session will be used if **boto3_session** is ``None``.
    pyarrow_additional_kwargs
        Forwarded to `to_pandas` method converting from PyArrow tables to Pandas DataFrame.
        Valid values include "split_blocks", "self_destruct", "ignore_metadata".
        e.g. pyarrow_additional_kwargs={'split_blocks': True}

    Returns
    -------
        Pandas DataFrame or Generator of Pandas DataFrames if chunksize is provided.

    Examples
    --------
    >>> import awswrangler as wr
    >>> df = wr.cleanrooms.read_sql_query(
    ...     sql='SELECT DISTINCT...',
    ...     membership_id='membership-id',
    ...     output_bucket='output-bucket',
    ...     output_prefix='output-prefix',
    ... )

    >>> import awswrangler as wr
    >>> df = wr.cleanrooms.read_sql_query(
    ...     analysis_template_arn='arn:aws:cleanrooms:...',
    ...     params={'param1': 'value1'},
    ...     membership_id='membership-id',
    ...     output_bucket='output-bucket',
    ...     output_prefix='output-prefix',
    ... )
    """
    client_cleanrooms = _utils.client(service_name="cleanrooms", session=boto3_session)

    if sql:
        sql_parameters: "ProtectedQuerySQLParametersTypeDef" = {
            "queryString": _process_sql_params(sql, params, engine_type="partiql")
        }
    elif analysis_template_arn:
        sql_parameters = {"analysisTemplateArn": analysis_template_arn}
        if params:
            sql_parameters["parameters"] = params
    else:
        raise exceptions.InvalidArgumentCombination("One of `sql` or `analysis_template_arn` must be supplied")

    query_id: str = client_cleanrooms.start_protected_query(
        type="SQL",
        membershipIdentifier=membership_id,
        sqlParameters=sql_parameters,
        resultConfiguration={
            "outputConfiguration": {
                "s3": {
                    "bucket": output_bucket,
                    "keyPrefix": output_prefix,
                    "resultFormat": "PARQUET",
                }
            }
        },
    )["protectedQuery"]["id"]

    _logger.debug("query_id: %s", query_id)
    path: str = wait_query(membership_id=membership_id, query_id=query_id, boto3_session=boto3_session)[
        "protectedQuery"
    ]["result"]["output"]["s3"]["location"]

    _logger.debug("path: %s", path)
    chunked: bool | int = False if chunksize is None else chunksize
    ret = s3.read_parquet(
        path=path,
        use_threads=use_threads,
        chunked=chunked,
        boto3_session=boto3_session,
        pyarrow_additional_kwargs=pyarrow_additional_kwargs,
    )

    _logger.debug("type(ret): %s", type(ret))
    kwargs: dict[str, Any] = {
        "path": path,
        "use_threads": use_threads,
        "boto3_session": boto3_session,
    }
    if chunked is False:
        if keep_files is False:
            s3.delete_objects(**kwargs)
        return ret
    return _delete_after_iterate(ret, keep_files, kwargs)
