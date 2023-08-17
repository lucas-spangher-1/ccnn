#!/bin/bash
#SBATCH --job-name=lucas_ccnn
#SBATCH -N 1
#SBATCH --gres=gpu
#SBATCH --time=7:00:00
#SBATCH -p sched_mit_psfc_gpu_r8

source /etc/profile

# Load necessary modules
module load anaconda3/2022.10

source /home/software/anaconda3/2022.10/etc/profile.d/conda.sh
conda activate will-env

. ./venv/bin/activate

export PYTHONUSERBASE=intentionally-disabled
# Run multiple instantiations of the WandB agent in parallel
export WANDB_API_KEY=19a95b1c7d3cc50ffeed9b952b0b7477bdcc0bd6
export WANDB_DIR=/dev/shm/ccnn
export WANDB_CACHE_DIR=/dev/shm/ccnn-cache
wandb agent "$1"

# Deactivate your virtual environment
conda deactivate