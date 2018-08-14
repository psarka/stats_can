# -*- coding: utf-8 -*-
""" Provides a python implementation of the Statistics Canada Web Data Service

https://www.statcan.gc.ca/eng/developers/wds/user-guide

Note: StatsCan uses cube/table interchangeably. I'm going to keep cube in my
function names where it maps to their api but otherwise I will use table.
Hence functions with cube in the function name will take tables as an argument
I'm not sure which is less confusing, it's annoying they weren't just
consistent.


Attributes
----------
SC_URL : str
    URL for the Statistics Canada REST api

TODO
----
Oh man, so much.
Missing api implementations:
    GetSeriesInfoFromCubePidCoord
    GetChangedSeriesDataFromCubePidCoord
    GetChangedSeriesDataFromVector
    GetDataFromCubePidCoordAndLatestNPeriods
    GetFullTableDownloadSDMX
    GetCodeSets
I'd like to look into saving downloaded tables as hdf rather than csv/json
If it works and is reasonably space efficient it would save processing time

Extend getChangedCubeList with a function that returns all tables updated
within a date range

Should probably build some tests

getBulkvectorfromrange should be extended to a method that returns a df,
same for vectors and n periods function

The whole thing only works in English right now. Add French support

@author: Ian Preston
"""
import re
import os
import json
import zipfile
import datetime as dt
import pandas as pd
import numpy as np
import requests
SC_URL = 'https://www150.statcan.gc.ca/t1/wds/rest/'


def get_changed_series_list():
    """https://www.statcan.gc.ca/eng/developers/wds/user-guide#a10-1

    Gets all series that were updated today.

    Returns
    -------
    list of dicts
        one for each vector and when it was released
    """
    url = SC_URL + 'getChangedSeriesList'
    result = requests.get(url)
    result = check_status(result)
    return result['object']


def get_changed_cube_list(date=dt.date.today()):
    """https://www.statcan.gc.ca/eng/developers/wds/user-guide#a10-2

    Parameters
    ----------
    date : datetime.date
        Date to check for table changes, defaults to current date

    Returns
    -------
    list of dicts
        one for each table and when it was updated
    """
    url = SC_URL + 'getChangedCubeList' + '/' + str(date)
    result = requests.get(url)
    result = check_status(result)
    return result['object']


def get_cube_metadata(tables):
    """https://www.statcan.gc.ca/eng/developers/wds/user-guide#a11-1

    Take a list of tables and return a list of dictionaries with their
    metadata

    Parameters
    ----------
    tables : str or list of str
        IDs of tables to get metadata for

    Returns
    -------
    list of dicts
        one for each table with its metadata
    """
    tables = parse_tables(tables)
    tables = [{'productId': t} for t in tables]
    url = SC_URL + 'getCubeMetadata'
    result = requests.post(url, json=tables)
    result.raise_for_status()
    result = check_status(result)
    return [r['object'] for r in result]


def get_series_info_from_cube_pid_coord():
    """ Not implemented yet

    https://www.statcan.gc.ca/eng/developers/wds/user-guide#a11-2"""
    pass


def get_series_info_from_vector(vectors):
    """https://www.statcan.gc.ca/eng/developers/wds/user-guide#a11-3

    Parameters
    ----------
    vectors: str or list of str
        vector numbers to get info for

    Returns
    -------
    List of dicts containing metadata for each v#
    """
    url = SC_URL + 'getSeriesInfoFromVector'
    chunks = chunk_vectors(vectors)
    final_list = []
    for chunk in chunks:
        vectors = [{'vectorId': v} for v in chunk]
        result = requests.post(url, json=vectors)
        result = check_status(result)
        final_list += result
    return [r['object'] for r in final_list]


def get_changed_series_data_from_cube_pid_coord():
    """ Not implemented yet

    https://www.statcan.gc.ca/eng/developers/wds/user-guide#a12-1"""
    pass


def get_changed_series_data_from_vector():
    """ Not implemented yet

    https://www.statcan.gc.ca/eng/developers/wds/user-guide#a12-2"""
    pass


def get_data_from_cube_pid_coord_and_latest_n_periods():
    """ Not implemented yet

    https://www.statcan.gc.ca/eng/developers/wds/user-guide#a12-3
    """
    pass


def get_data_from_vectors_and_latest_n_periods(vectors, periods):
    """ https://www.statcan.gc.ca/eng/developers/wds/user-guide#a12-4

    Parameters
    ----------
    vectors: str or list of str
        vector numbers to get info for
    periods: int
        number of periods (starting at latest) to retrieve data for

    Returns
    -------
    List of dicts containing data for each vector

    ToDo
    ----
    Add chunking to handle over 300 vectors
    """
    url = SC_URL + 'getDataFromVectorsAndLatestNPeriods'
    chunks = chunk_vectors(vectors)
    final_list = []
    for chunk in chunks:
        periods_l = [periods for i in range(len(chunk))]
        json = [
            {'vectorId': v, 'latestN': n} for v, n in zip(chunk, periods_l)
            ]
        result = requests.post(url, json=json)
        result = check_status(result)
        final_list += [r['object'] for r in result]
    return final_list


def get_bulk_vector_data_by_range(
        vectors, start_release_date, end_release_date
):
    """https://www.statcan.gc.ca/eng/developers/wds/user-guide#a12-5
    Parameters
    ----------
    vectors: str or list of str
        vector numbers to get info for
    start_release_date: datetime.date
        start release date for the data
    end_release_date: datetime.date
        end release date for the data

    Returns
    -------
    List of dicts containing data for each vector
    """
    url = SC_URL + 'getBulkVectorDataByRange'
    start_release_date = str(start_release_date) + "T13:00"
    end_release_date = str(end_release_date) + "T13:00"
    chunks = chunk_vectors(vectors)
    final_list = []
    for vector_ids in chunks:
        result = requests.post(
            url,
            json={
                "vectorIds": vector_ids,
                "startDataPointReleaseDate": start_release_date,
                "endDataPointReleaseDate": end_release_date
                }
            )
        result = check_status(result)
        final_list += [r['object'] for r in result]
    return final_list


def get_full_table_download(table, csv=True):
    """https://www.statcan.gc.ca/eng/developers/wds/user-guide#a12-6
    https://www.statcan.gc.ca/eng/developers/wds/user-guide#a12-7

    Take a table name and return a url to a zipped file of that table

    Parameters
    ----------
    table: str
        table name to download
    csv: boolean, default True
        download in CSV format, if not download SDMX
    """
    table = parse_tables(table)[0]
    if csv:
        url = SC_URL + 'getFullTableDownloadCSV/' + table + '/en'
    else:
        url = SC_URL + 'getFullTableDownloadSDMX/' + table
    result = requests.get(url)
    result = check_status(result)
    return result['object']


def get_code_sets():
    """ Not implemented yet

    https://www.statcan.gc.ca/eng/developers/wds/user-guide#a13-1
    """
    pass


def check_status(results):
    """Make sure list of results succeeded

    Parameters
    ----------
    results : list of dicts, or dict
        JSON from an API call parsed as a dictionary
    """
    results.raise_for_status()
    results = results.json()

    def check_one_status(result):
        """Do the check on an individual result"""
        if result['status'] != 'SUCCESS':
            raise RuntimeError(str(result['object']))
    if isinstance(results, list):
        for result in results:
            check_one_status(result)
    else:
        check_one_status(results)
    return results


def parse_tables(tables):
    """ Basic cleanup of table or tables to numeric


    Strip out hyphens or other non-numeric characters from a list of tables
    or a single table
    Table names in StatsCan often have a trailing -01 which isn't necessary
    So also take just the first 8 characters.
    This function by no means guarantees you have a clean list of valid tables,
    but it's a good start.

    Parameters
    ----------
    tables : list of str or str
        A string or list of strings of table names to be parsed

    Returns
    -------
    list of str
        tables with unnecessary characters removed
    """
    def parse_table(table):
        """Clean up one table string"""
        return re.sub(r'\D', '', table)[:8]

    if isinstance(tables, str):
        return [parse_table(tables)]
    return [parse_table(t) for t in tables]


def parse_vectors(vectors):
    """ Basic cleanup of vector or vectors

    Strip out V from V#s. Similar to parse tables, this by no means guarantees
    a valid entry, just helps with some standard input formats

    Parameters
    ----------
    vectors : list of str or str
        A string or list of strings of vector names to be parsed

    Returns
    -------
    list of str
        vectors with unnecessary characters removed
    """
    def parse_vector(vector):
        """Strip string to numeric elements only"""
        if isinstance(vector, int):  # Already parsed earlier
            return vector
        return int(re.sub(r'\D', '', vector))

    if isinstance(vectors, str):
        return [parse_vector(vectors)]
    elif isinstance(vectors, int):
        return [parse_vector(vectors)]
    return [parse_vector(v) for v in vectors]


def chunk_vectors(vectors):
    """api calls max out at 300 vectors so break list into chunks"""
    MAX_CHUNK = 250
    vectors = parse_vectors(vectors)
    chunks = [
        vectors[i:i + MAX_CHUNK] for i in range(0, len(vectors), MAX_CHUNK)
        ]
    return chunks


def get_tables_for_vectors(vectors):
    """ get a list of dicts mapping vectors to tables

    Parameters
    ----------
    vectors : list of str or str
        Vectors to find tables for

    Returns
    -------
    list of dict
        keys for each vector number return the table, plus a key for
        'all_tables' that has a list of unique tables used by vectors
    """
    vectors = parse_vectors(vectors)
    v_json = get_series_info_from_vector(vectors)
    tables_list = {j['vectorId']: str(j['productId']) for j in v_json}
    tables_list['all_tables'] = []
    for vector in vectors:
        if tables_list[vector] not in tables_list['all_tables']:
            tables_list['all_tables'].append(tables_list[vector])
    return tables_list


def table_subsets_from_vectors(vectors):
    """get a list of dicts mapping tables to vectors

    Parameters
    ----------
    vectors : list of str or str
        Vectors to find tables for

    Returns
    -------
    list of dict
        keys for each table used by the vectors, matched to a list of vectors
    """
    start_tables_dict = get_tables_for_vectors(vectors)
    tables_dict = {t: [] for t in start_tables_dict['all_tables']}
    vecs = list(start_tables_dict.keys())[:-1]  # all but the all_tables key
    for vec in vecs:
        tables_dict[start_tables_dict[vec]].append(vec)
    return tables_dict


def test():
    print("right module")


def vectors_to_df(
    vectors, periods=1, start_release_date=None, end_release_date=None
):
    """data frame of vectors with n periods data or over range of release dates

    Wrapper on get_bulk_vector_data_by_range and
    get_data_from_vectors_and_latest_n_periods function to turn the resulting
    list of JSONs into a DataFrame

    Parameters
    ----------
    vectors: str or list of str
        vector numbers to get info for
    periods: int
        number of periods to retrieve data for
    start_release_date: datetime.date
        start release date for the data
    end_release_date: datetime.date
        end release date for the data

    Returns
    -------
    DataFrame with vectors as columns and ref_date as the index (not release)
    """
    df = pd.DataFrame()
    if ((end_release_date is None) | (start_release_date is None)):
        start_list = get_data_from_vectors_and_latest_n_periods(
            vectors, periods
            )
    else:
        start_list = get_bulk_vector_data_by_range(
            vectors, start_release_date, end_release_date
            )
    for vec in start_list:
        name = "v" + str(vec['vectorId'])
        ser = pd.DataFrame(vec['vectorDataPoint'])
        ser.set_index('refPer', inplace=True)
        ser.index = pd.to_datetime(ser.index)
        ser.rename(columns={'value': name}, inplace=True)
        ser = ser[name]
        df = pd.concat([df, ser], axis=1, sort=True)
    return df


def download_tables(tables, path=os.getcwd()):
    """
    Download a json file and zip of CSVs for a list of tables to path
    Input: a list of tables
    Output: Null, but it saves json and CSV files to path for each table
    """
    oldpath = os.getcwd()
    os.chdir(path)
    metas = get_cube_metadata(tables)
    for meta in metas:
        product_id = meta['productId']
        csv_url = get_full_table_download(product_id)
        csv_file = product_id + '-eng.zip'
        # Thanks http://evanhahn.com/python-requests-library-useragent/
        response = requests.get(
            csv_url,
            stream=True,
            headers={'user-agent': None}
            )
        # Thanks https://bit.ly/2sPYPYw
        with open(csv_file, 'wb') as handle:
            for chunk in response.iter_content(chunk_size=512):
                if chunk:  # filter out keep-alive new chunks
                    handle.write(chunk)
        json_file = product_id + '.json'
        with open(json_file, 'w') as outfile:
            json.dump(meta, outfile)
    os.chdir(oldpath)


def update_tables(path=os.getcwd()):
    """
    Grabs the json files in path, checks them against the metadata on
    StatsCan and grabs updated tables where there have been changes
    There isn't actually a "last modified date" part to the metadata
    What I'm doing is comparing the latest reference period. Almost all
    data changes will at least include incremental releases, so this should
    capture what I want
    Returns a list of the tables that were updated
    """
    oldpath = os.getcwd()
    os.chdir(path)
    local_jsons = []
    for file in os.listdir():
        if file.endswith('.json'):
            with open(file) as f_name:
                local_jsons.append(json.load(f_name))
    tables = [j['productId'] for j in local_jsons]
    remote_jsons = get_cube_metadata(tables)
    update_table_list = []
    for local, remote in zip(local_jsons, remote_jsons):
        if local['cubeEndDate'] != remote['cubeEndDate']:
            update_table_list.append(local['productId'])
    download_tables(update_table_list, path)
    os.chdir(oldpath)
    return update_table_list


def table_to_dataframe(table, path=os.getcwd()):
    """
    Reads a StatsCan table into a pandas DataFrame
    If a zip file of the table does not exist in path, downloads it
    returns
    """
    oldpath = os.getcwd()
    os.chdir(path)
    # Parse tables returns a list, can only do one table at a time here though
    table = parse_tables(table)[0]
    table_zip = table + '-eng.zip'
    if not os.path.isfile(table_zip):
        download_tables([table], path)
    csv_file = table + '.csv'
    with zipfile.ZipFile(table_zip) as myzip:
        with myzip.open(csv_file) as myfile:
            col_names = pd.read_csv(myfile, nrows=0).columns
        # reopen the file or it misses the first row
        with myzip.open(csv_file) as myfile:
            types_dict = {'VALUE': float}
            types_dict.update(
                {col: str for col in col_names if col not in types_dict}
                )
            df = pd.read_csv(
                myfile,
                dtype=types_dict
                )

    possible_cats = [
        'GEO', 'DGUID', 'STATUS', 'SYMBOL', 'TERMINATED', 'DECIMALS',
        'UOM', 'UOM_ID', 'SCALAR_FACTOR', 'SCALAR_ID', 'VECTOR', 'COORDINATE',
        'Wages', 'National Occupational Classification for Statistics (NOC-S)',
        'Supplementary unemployment rates', 'Sex', 'Age group',
        'Labour force characteristics', 'Statistics', 'Data type'
        ]
    actual_cats = [col for col in possible_cats if col in col_names]
    df[actual_cats] = df[actual_cats].astype('category')
    try:
        df['REF_DATE'] = pd.to_datetime(df['REF_DATE'], format='%Y-%m')
    except TypeError:
        df['REF_DATE'] = pd.to_datetime(df['REF_DATE'])
    os.chdir(oldpath)
    return df


def get_classic_vector_format_df(vectors, path, start_date=None):
    """
    Like oldschool CANSIM, this will return a single dataframe with V numbers
    as columns, indexed on date
    Inputs:
        vectors: list of vectors to be read in
        path: path to zipped StatsCan tables
        start_date: optional earliest reference date to include
    Returns: A DataFrame as described above
    """
    # Preserve an initial copy of the list for ordering, parsed and then
    # converted to string for consistency in naming
    vectors_ordered = parse_vectors(vectors)
    vectors_ordered = ['v' + str(v) for v in vectors_ordered]
    table_vec_dict = table_subsets_from_vectors(vectors)
    tables = list(table_vec_dict.keys())
    tables_dfs = {}
    columns = ['REF_DATE', 'VECTOR', 'VALUE']
    for table in tables:
        tables_dfs[table] = table_to_dataframe(table, path)[columns]
        df = tables_dfs[table]  # save me some typing
        vec_list = ['v' + str(v) for v in table_vec_dict[table]]
        df = df[df['VECTOR'].isin(vec_list)]
        if start_date is not None:
            start_date = np.datetime64(start_date)
            df = df[df['REF_DATE'] >= start_date]
        df = df.pivot(index='REF_DATE', columns='VECTOR', values='VALUE')
        df.columns = list(df.columns)  # remove categorical index
        tables_dfs[table] = df
    final_df = tables_dfs[tables[0]]
    for table in tables[1:]:
        final_df = pd.merge(
            final_df, tables_dfs[table],
            how='outer',
            left_index=True, right_index=True
            )
    final_df = final_df[vectors_ordered]
    return final_df
