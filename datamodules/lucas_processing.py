import torch
from torch.utils.data import Dataset
from sklearn.preprocessing import RobustScaler
import random
from typing import List
import math
import pandas as pd 
import random
import numpy as np
import copy


class ModelReadyDataset(Dataset):
    """Torch Dataset for model-ready data.

    Args:
        shots (list): List of shots.
        inds (list): List of shot indices for reference.
        end_cutoff (float): Fraction of the shot to use as the end.
        end_cutoff_timesteps (int): Number of timesteps to cut off the end of the shot.
        max_length (int): Maximum length of the input sequence.

    Attributes:
        xs (list): List of input embeddings.
        ys (list): List of labels.
        metas (list) = List of shot metadata like machine, index, etc
    """

    def __init__(
        self,
        shots: List,
        inds: List,
        end_cutoff,
        end_cutoff_timesteps,
        machine_hyperparameters,
        taus,
        max_length=2048,
        len_aug: bool = False,
        seed: int = 42,
        len_aug_args: dict = {},
    ):
        self.len_aug = len_aug
        self.len_aug_args = len_aug_args
        self.rand = random.Random(seed)
        self.taus = taus

        self.xs = []
        self.ys = []
        self.metas = []
        self.machines = []

        for shot, ind in zip(shots, inds):
            shot_df = shot["data"]
            o = torch.tensor(
                [shot["label"] * machine_hyperparameters[shot["machine"]]],
                dtype=torch.float32,
            )

            shot_end = 0
            if end_cutoff:
                shot_end = int(len(shot_df) * (end_cutoff))
            elif end_cutoff_timesteps:
                shot_end = int(len(shot_df) - end_cutoff_timesteps)
            else:
                raise Exception(
                    "Must provide either end_cutoff or end_cutoff_timesteps"
                )

            d = torch.tensor(shot_df[:shot_end], dtype=torch.float32)

            # test if the shot's length is between 15 and max_length
            if 15 <= len(d) <= max_length:
                self.xs.append(d)
                self.ys.append(o)
                self.metas.append(
                    {
                        "ind": ind,
                        "shot_len": shot_end,
                        "machine": shot["machine"],
                    }
                )

    def robustly_scale(self):
        """Robustly scale the data.

        Returns:
            scaler (object): Scaler used to scale the data."""

        scaler = RobustScaler()
        combined = torch.cat(self.xs)
        scaler.fit(combined)
        for i in range(len(self.xs)):
            self.xs[i] = torch.from_numpy(
                scaler.transform(self.xs[i]).astype("float32")
            )

        return scaler

    def robustly_scale_with_another_scaler(self, scaler):
        """Robustly scale the data with another scaler.

        Args:
            scaler (object): Scaler to use to scale the data.
        """

        for i in range(len(self.xs)):
            self.xs[i] = torch.from_numpy(
                scaler.transform(self.xs[i]).astype("float32")
            )

        return

    def __len__(self):
        return len(self.xs)

    def __getitem__(self, idx):
        """
        Returns: a tuple of (input_embeds, labels, len) where
            inputs_embeds (tensor): Input embeddings.
            labels (tensor): a 0/1 label for disruptions/no disruption
            len (int): Length of the shot.
        """
        x, y, length = self.xs[idx], self.ys[idx], self.metas[idx]["shot_len"]
        m = self.metas[idx]["machine"]
        tau = self.taus[m]

        if self.len_aug:
            x, y, length = length_augmentation(
                x, y, length, tau, self.rand, **self.len_aug_args
            )

        assert x.shape[0] == length
        return x, y, length


class ModelReadyDatasetStatePretraining(ModelReadyDataset):
    def __init__(
        self,
        shots: List,
        inds: List,
        end_cutoff,
        end_cutoff_timesteps,
        machine_hyperparameters,
        taus,
        max_length=2048,
        len_aug: bool = False,
        seed: int = 42,
        len_aug_args: dict = {},):

        self.inputs_embeds = []
        self.labels = []
        self.shot_inds = []
        self.end_cutoff_timesteps = end_cutoff_timesteps
        self.machine_hyperparameters = machine_hyperparameters
        self.taus = taus
        self.shots = []

        self.max_length = max_length
        self.num_disruptions = 0
        self.machines = []
        self.is_disruptive = []

        self.len_aug = len_aug
        self.len_aug_args = len_aug_args
        self.rand = random.Random(seed)
        self.taus = taus

        self.xs = []
        self.ys = []
        self.metas = []
        self.machines = []

        for shot, ind in zip(shots, inds):
            shot_df = shot["data"]
            o = torch.tensor(
                [shot["label"] * machine_hyperparameters[shot["machine"]]],
                dtype=torch.float32,
            )
            
            shot_end = int(len(shot_df) - end_cutoff_timesteps)

            # test if shot_end is between 10 and max_length
            if not 10 <= shot_end < max_length:
                continue

            if isinstance(shot_df, pd.DataFrame):
                d = torch.tensor(shot_df[:shot_end].values, dtype=torch.float32)
                d_target = torch.tensor(shot_df[1:shot_end].values, dtype=torch.float32)
            elif isinstance(shot_df, np.ndarray):
                d = torch.tensor(shot_df[:shot_end], dtype=torch.float32)
                d_target = torch.tensor(shot_df[1:shot_end+1], dtype=torch.float32)
            elif isinstance(shot_df, torch.tensor):
                d = shot_df[:shot_end].clone().detach()
                d_target = shot_df[1:shot_end].clone().detach()
            else:
                raise ValueError('Unknown data type for shot_df')

            self.inputs_embeds.append(d)
            self.labels.append(d_target)
            self.machines.append(shot['machine'])
            self.is_disruptive.append(int(np.round(shot['label'])))
            self.shots.append(shot['shot'])
            self.xs.append(d)
            self.ys.append(o)
            self.metas.append(
                {
                    "ind": ind,
                    "shot_len": shot_end,
                    "machine": shot["machine"],
                }
            )

    def subselect_feature_columns(self):
        self.labels = [x[:, [0, 1, 2, 4, 8, 9, 10, 11, 12]] for x in self.labels]


def get_train_test_indices_from_Jinxiang_cases(
        dataset, case_number, new_machine, seed):
    """Get train and test indices for Jinxiang's cases.

    Args:
        dataset (object): Dictionary to split of form: {"label": int, "data": np.array, "machine": str}
        case_number (int): Case number. 
            Cases 1 - 12 refer to Jinxiang's cases
            Case 13 is Francesco's case of only training and testing on non-disruptions. 
        new_machine (str): Name of the new machine.

    Returns:
        train_indices (list): List of indices for the training set.
        test_indices (list): List of indices for the testing set.
    """

    rand = random.Random(seed)

    existing_machines = {"cmod", "d3d", "east"}
    existing_machines.remove(new_machine)
    train_indices = []

    new_machine_indices = {
        "non_disruptive": [],
        "disruptive": []
    }

    new_machine_disruption_count = 0

    for key, value in dataset.items():
        if value["machine"] == new_machine:

            # new machine non disruptions
            if value["label"] == 0:
                new_machine_indices["non_disruptive"].append(key)
                if case_number in {1, 2, 4, 5, 7, 8, 9, 13}:
                    train_indices.append(key)
                if case_number == 3:
                    if random.random() < 0.5:
                        train_indices.append(key)
                if case_number in {10, 11, 12}:
                    if random.random() < 0.33:
                        train_indices.append(key)
            else:
            # new machine disruptions
                new_machine_indices["disruptive"].append(key)
                if case_number in {7, 8, 9, 10, 11, 12}:
                    # add all disruptions
                    train_indices.append(key)
                
                if case_number in {1, 3, 4, 5}:
                    # add 25 disruptions
                    if new_machine_disruption_count < 25:
                        train_indices.append(key)
                        new_machine_disruption_count += 1

        elif value["machine"] in existing_machines:
            # existing non disruptions
            if case_number in {5, 6, 8, 13} and value["label"] == 0:
                train_indices.append(key)
            if case_number == 11:
                if random.random() < 0.2:
                    train_indices.append(key)
            
            # existing disruptions
            if case_number in {1, 2, 3, 5, 6, 7, 8, 10} and value["label"] == 1:
                train_indices.append(key)

    rand.shuffle(train_indices)

    # Create test set by sampling 20% of the new machine's shots
    test_indices = rand.sample(new_machine_indices["non_disruptive"], len(new_machine_indices["non_disruptive"]) // 6)

    if case_number != 13:
        test_indices.extend(rand.sample(new_machine_indices["disruptive"], max(len(new_machine_indices["disruptive"]) // 6, 20)))

    # Remove test indices from training set if they were added earlier
    train_indices = [index for index in train_indices if index not in test_indices]

    # Counting the number of disruptive shots in the train set
    train_disruptive_shots = sum(dataset[index]["label"] == 1 for index in train_indices)
    train_non_disruptive_shots = sum(dataset[index]["label"] == 0 for index in train_indices)
    print(f"Number of disruptive shots in the train set: {train_disruptive_shots}")
    print(f"Number of non-disruptive shots in the train set: {train_non_disruptive_shots}")

    # Counting the number of disruptive shots in the test set
    test_disruptive_shots = sum(dataset[index]["label"] == 1 for index in test_indices)
    test_non_disruptive_shots = sum(dataset[index]["label"] == 0 for index in test_indices)
    print(f"Number of disruptive shots in the test set: {test_disruptive_shots}")
    print(f"Number of non-disruptive shots in the test set: {test_non_disruptive_shots}")


    return train_indices, test_indices


def get_class_weights(train_dataset):
    """Get class weights for the training set.

    Args:
        train_dataset (object): Training set.

    Returns:
        class_weights (list): List of class weights.
    """
    class_counts = {}

    for i in range(len(train_dataset)):
        df = train_dataset[i]
        label = int(df["labels"][0])
        if label in class_counts.keys():
            class_counts[label] += 1
        else:
            class_counts[label] = 1
    class_weights = [
        class_counts[key] / sum(class_counts.values()) for key in class_counts.keys()
    ]

    print("class weights: ")
    print(class_weights)

    return class_weights


def length_augmentation(
    x,
    y,
    length,
    tau,
    rand: random.Random,
    tiny_clip_max_len=30,
    tiny_clip_prob=0.05,
    disrupt_trim_max=10,
    disrupt_trim_prob=0.2,
    nondisr_cut_min=15,
    nondisr_cut_prob=0.3,
    tau_trim_prob=0.2,
    tau_trim_max=10,
):
    # TODO: actually do a logical or on all these cases
    """Perform length augmentation clipping.

    Args:
        x (torch.Tensor): the input x tensor
        y (torch.Tensor): the torch tensor with the y input
        length (int): the length of x
        rand (random.Random): the random sampler to draw from
        tiny_clip_max_len (int, optional): The maximum length to trim a sequence to when
            doing tiny clipping. Defaults to 30.
        tiny_clip_prob (float, optional): The probability of doing tiny clipping.
            Defaults to 0.05.
        disrupt_trim_max (int, optional): The maximum amount to remove from the end of
            a disruption when doing trimming. Defaults to 10.
        disrupt_trim_prob (float, optional): The probability of doing disruption
            trimming. Defaults to 0.2.
        nondisr_cut_min (int, optional): The minimum size to cut non-disruptions to.
            Defaults to 15.
        nondisr_cut_prob (float, optional): The probability of doing non-disruption
            trimming. Defaults to 0.3.
        tau_trim_prob (float, optional): the probability we do tau trimming
        tau_trim_max (int, optional): the maximum we cut from the end of the seq
            when doing tau trimming

    Returns:
        (x, y, len): the x, y, len to use
    """
    new_len = None

    if rand.random() < tiny_clip_prob:
        # sample len in [1, tiny_clip_max_len]
        new_len = math.ceil(rand.random() * tiny_clip_max_len)
        new_len = min(new_len, length)
        return x[:new_len], torch.tensor(0), new_len

    elif y == 1 and rand.random() < disrupt_trim_prob:
        # sample len in [len-disrupt_trim_max, len]
        new_len = length - math.floor(rand.random() * disrupt_trim_max)
        new_len = min(new_len, length)
        return x[:new_len], y, new_len

    elif y == 1 and rand.random() < tau_trim_prob:
        # sample len in [len-tau_trim_max, len]
        new_len = length - math.floor(rand.random() * tau_trim_max)
        new_len = min(new_len, length)
        if new_len < length - tau:
            y = 0
        return x[:new_len], y, new_len

    elif y == 0 and rand.random() < nondisr_cut_prob:
        # sample len in [nondisr_cut_min, len]
        new_len = nondisr_cut_min + math.ceil(
            (length - nondisr_cut_min) * rand.random()
        )
        new_len = min(new_len, length)
        return x[:new_len], y, new_len

    else:
        return x, y, length
