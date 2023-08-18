#!/bin/bash
#SBATCH --job-name=ccnn_sweep
#SBATCH -N 1
#SBATCH --gres=gpu
#SBATCH --time=7:00:00
#SBATCH -p sched_mit_psfc_gpu_r8

source /etc/profile

# Load necessary modules
module load anaconda3/2022.10

source /home/software/anaconda3/2022.10/etc/profile.d/conda.sh
conda activate will-env


# cd /home/spangher/ccnn
. ./venv/bin/activate

# Ignore the bogus local user packages on the host
export PYTHONUSERBASE=intentionally-disabled
# Run multiple instantiations of the WandB agent in parallel
export WANDB_API_KEY=7385069f57b00860da0e7add0bdc6eba19fb07cd
wandb agent "$1"

# Deactivate your virtual environment
conda deactivate