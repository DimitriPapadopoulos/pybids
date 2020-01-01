from os.path import split
from bids.variables import load_variables
from collections import OrderedDict
import numpy as np


def _make_passthrough_contrast(level, contrast_names, type="t"):
    block = OrderedDict(Level=level, Name=level,
                        Model={'X': contrast_names})
    contrasts = []
    for cn in contrast_names:
        cdict = OrderedDict(Name=level.lower() + "_" + cn, ConditionList=[cn],
                            Weights=[1], Type=type)
        contrasts.append(cdict)
    block["Contrasts"] = contrasts
    return block


def auto_model(layout, scan_length=None, one_vs_rest=False):
    """Create a simple default model for each of the tasks in a BIDSLayout.
    Contrasts each trial type against all other trial types and trial types
    at the run level and then uses dummy contrasts at each other level
    present to aggregate these results up.

    Parameters
    ----------
    layout : :obj:`bids.layout.BIDSLayout`
        A BIDSLayout instance
    scan_length : int
        Scan length for loading event variables in cases
        where the scan length can not be read from the nifti.
        Primarily for testing.
    one_vs_rest : bool
        Set to True if you would like to autogenerate
        contrasts of each trial type against everyother trialtype.

    Returns
    -------
    list
        list of model dictionaries for each task
    """

    base_name = split(layout.root)[-1]
    tasks = layout.entities['task'].unique()
    task_models = []

    for task_name in tasks:
        # Populate model meta-data
        model = OrderedDict()
        model["Name"] = "_".join([base_name, task_name])
        model["Description"] = ("Autogenerated model for the %s task from %s" %
                                (task_name, base_name))
        model["Input"] = {"Task": task_name}
        steps = []

        # Make run level block
        transformations = OrderedDict(Name='Factor', Input=['trial_type'])
        run = OrderedDict(Level='Run', Name='Run',
                          Transformations=[transformations])

        # Get trial types
        run_nodes = load_variables(layout, task=task_name, levels=['run'],
                                   scan_length=scan_length)

        evs = []
        for n in run_nodes.nodes:
            evs.extend(n.variables['trial_type'].values.values)
        trial_types = np.unique(evs)
        trial_type_factors = ["trial_type." + tt for tt in trial_types]

        # Add HRF
        run['Transformations'].append(
                OrderedDict(Name='Convolve', Input=trial_type_factors))

        run_model = OrderedDict(X=trial_type_factors)
        run["Model"] = run_model

        if one_vs_rest:
            # If there are multiple trial types, build contrasts
            contrasts = []
            for i, tt in enumerate(trial_types):
                cdict = OrderedDict()
                if len(trial_types) > 1:
                    cdict["Name"] = "run_" + tt + "_vs_others"
                else:
                    cdict["Name"] = "run_" + tt
                cdict["ConditionList"] = trial_type_factors

                # Calculate weights for contrast
                weights = np.ones(len(trial_types))
                try:
                    weights[trial_types != tt] = -1.0 / (len(trial_types) - 1)
                except ZeroDivisionError:
                    pass
                cdict["Weights"] = list(weights)

                cdict["Type"] = "t"
                contrasts.append(cdict)

            run["Contrasts"] = contrasts
        steps.append(run)

        if one_vs_rest:
            # if there are multiple sessions, t-test run level contrasts at
            # session level
            sessions = layout.get_sessions()
            if len(sessions) > 1:
                # get contrasts names from previous block
                contrast_names = [cc["Name"] for cc in steps[-1]["Contrasts"]]
                steps.append(_make_passthrough_contrast(
                    "Session", contrast_names, "FEMA"))

            subjects = layout.get_subjects()
            if len(subjects) > 1:
                # get contrasts names from previous block
                contrast_names = [cc["Name"] for cc in steps[-1]["Contrasts"]]
                steps.append(_make_passthrough_contrast(
                    "Subject", contrast_names, "FEMA"))

            # get contrasts names from previous block
            contrast_names = [cc["Name"] for cc in steps[-1]["Contrasts"]]
            steps.append(_make_passthrough_contrast(
                "Dataset", contrast_names, "t"))

        model["Steps"] = steps
        task_models.append(model)

    return task_models
