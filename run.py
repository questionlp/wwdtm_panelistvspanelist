# -*- coding: utf-8 -*-
# Copyright (c) 2018-2019 Linh Pham
# wwdtm_panelistvspanelist is relased under the terms of the Apache License 2.0
"""WWDTM Panelist vs Panelist Report Generator"""

import collections
from datetime import datetime
import json
import os
import slugify
import time
import mysql.connector
import pytz

from jinja2 import Environment, FileSystemLoader

def load_config():
    """Load configuration file containing database connection details"""

    with open('config.json', 'r') as config_file:
        config_dict = json.load(config_file)
        return config_dict

def retrieve_panelists(database_connection):
    """Retrieve panelists from the Stats Page database"""

    panelists = []
    try:
        cursor = database_connection.cursor()
        query = ("SELECT DISTINCT p.panelist FROM ww_showpnlmap pm "
                 "JOIN ww_panelists p ON p.panelistid = pm.panelistid "
                 "WHERE pm.panelistscore IS NOT NULL "
                 "AND p.panelist <> '<Multiple>' "
                 "ORDER BY p.panelist ASC;")
        cursor.execute(query, )
        result = cursor.fetchall()
        cursor.close()

        for panelist in result:
            panelists.append(panelist[0])

        return panelists
    except mysql.connector.Error:
        return

def retrieve_panelist_appearances(panelists, database_connection):
    """Retrieve panelist appearances from the Stats Page database"""

    panelist_appearances = collections.OrderedDict()
    for panelist in panelists:
        try:
            appearances = []
            cursor = database_connection.cursor()
            query = ("SELECT s.showdate FROM ww_showpnlmap pm "
                     "JOIN ww_panelists p ON p.panelistid = pm.panelistid "
                     "JOIN ww_shows s ON s.showid = pm.showid "
                     "WHERE p.panelist = %s "
                     "AND pm.panelistscore IS NOT NULL "
                     "AND s.bestof = 0 "
                     "AND s.repeatshowid IS NULL "
                     "ORDER BY s.showdate ASC;")
            cursor.execute(query, (panelist,))
            result = cursor.fetchall()
            cursor.close()

            if result:
                for appearance in result:
                    appearances.append(appearance[0].isoformat())

                panelist_appearances[panelist] = appearances
        except mysql.connector.Error:
            return

    return panelist_appearances

def retrieve_show_scores(database_connection):
    """Retrieve scores for each show and panelist from the Stats Page Database"""

    shows = collections.OrderedDict()

    try:
        cursor = database_connection.cursor()
        query = ("SELECT s.showdate, p.panelist, pm.panelistscore FROM ww_showpnlmap pm "
                 "JOIN ww_panelists p ON p.panelistid = pm.panelistid "
                 "JOIN ww_shows s ON s.showid = pm.showid "
                 "WHERE s.bestof = 0 "
                 "AND s.repeatshowid IS NULL "
                 "AND pm.panelistscore IS NOT NULL "
                 "ORDER BY s.showdate ASC, pm.panelistscore DESC;")
        cursor.execute(query, )
        result = cursor.fetchall()
        cursor.close()

        if result:
            for show in result:
                show_date = show[0].isoformat()
                if show_date not in shows:
                    shows[show_date] = collections.OrderedDict()

                panelist = show[1]
                panelist_score = show[2]
                shows[show_date][panelist] = panelist_score

        return shows
    except mysql.connector.Error:
        return

def generate_panelist_vs_panelist_results(panelists, panelist_appearances, show_scores):
    """Generate panelist vs panelist results"""

    panelist_list = panelists
    pvp_results = collections.OrderedDict()
    for panelist_a in panelists:
        pvp_results[panelist_a] = collections.OrderedDict()
        for panelist_b in panelist_list:
            if panelist_a != panelist_b:
                panelist_a_appearances = panelist_appearances[panelist_a]
                panelist_b_appearances = panelist_appearances[panelist_b]
                a_b_intersect = list(set(panelist_a_appearances) & set(panelist_b_appearances))
                a_b_intersect.sort()

                pvp_results[panelist_a][panelist_b] = collections.OrderedDict()
                wins = 0
                draws = 0
                losses = 0
                for show in a_b_intersect:
                    panelist_a_score = show_scores[show][panelist_a]
                    panelist_b_score = show_scores[show][panelist_b]
                    if panelist_a_score > panelist_b_score:
                        wins = wins + 1
                    elif panelist_a_score == panelist_b_score:
                        draws = draws + 1
                    else:
                        losses = losses + 1

                pvp_results[panelist_a][panelist_b]["wins"] = wins
                pvp_results[panelist_a][panelist_b]["draws"] = draws
                pvp_results[panelist_a][panelist_b]["losses"] = losses

    return pvp_results

def render_report(app_environment,
                  panelist_vs_panelist_results,
                  google_analytics_property_code):
    """Render report using a Jinja2 template"""
    # Setup Jinja2 Template
    template_loader = FileSystemLoader('./html')
    template_env = Environment(loader=template_loader,
                               trim_blocks=True,
                               lstrip_blocks=True)
    template_file = 'template.html'
    template = template_env.get_template(template_file)

    # Generate timestamp to include at the bottom of the rendered page
    time_zone = pytz.timezone('America/Los_Angeles')
    rendered_date_time = datetime.now(time_zone)
    rendered_at = rendered_date_time.strftime('%A %B %d, %Y %H:%M:%S %Z')

    rendered_report = template.render(slugify=slugify,
                                      app_environment=app_environment,
                                      results=panelist_vs_panelist_results,
                                      rendered_at=rendered_at,
                                      ga_property_code=google_analytics_property_code)
    print(rendered_report)
    return

def main():
    """Bootstrap database connection, retrieve data, generate results and render report"""

    # Read in APP_ENV environment variable (if not set, default to "development")
    app_environment = os.getenv("APP_ENV", "development").strip().lower()

    # Read in GA_PROP environment variable (if not set, default to "")
    ga_property_code = os.getenv("GA_PROP", "").strip()

    # Retrieve database connection info from config
    database_config = load_config()

    # Set up database connection
    database_connection = mysql.connector.connect(**database_config["database"])

    # Retrieve panelists and panelist appearances
    panelists = retrieve_panelists(database_connection)
    panelist_appearances = retrieve_panelist_appearances(panelists, database_connection)

    # Retrieve show scores
    show_scores = retrieve_show_scores(database_connection)

    # Calculate panelist v panelist results
    results = generate_panelist_vs_panelist_results(panelists, panelist_appearances, show_scores)

    # Render Report
    render_report(app_environment, results, ga_property_code)
    return

# Only run if executed as a script and not imported
if __name__ == '__main__':
    main()
