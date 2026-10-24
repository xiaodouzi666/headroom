"""Offline synthetic GPT-2-medium Trainer OOM fixture; tiny CPU smoke is separate."""

import argparse
import json

import torch
from torch.utils.data import Dataset
from transformers import GPT2Config, GPT2LMHeadModel, Trainer, TrainingArguments, set_seed


class SyntheticTokens(Dataset):
    def __init__(self, length, sequence_length, vocabulary, seed):
        self.length = length
        self.sequence_length = sequence_length
        self.vocabulary = vocabulary
        self.seed = seed

    def __len__(self):
        return self.length

    def __getitem__(self, index):
        generator = torch.Generator().manual_seed(self.seed + index)
        tokens = torch.randint(self.vocabulary, (self.sequence_length,), generator=generator)
        return {
            "input_ids": tokens,
            "labels": tokens.clone(),
            "attention_mask": torch.ones_like(tokens),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("full", "cpu-smoke"), default="full")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--batch_size", type=int, default=None)
    args = parser.parse_args()
    if args.profile == "cpu-smoke" and args.device != "cpu":
        parser.error("cpu-smoke is only a CPU implementation check")
    if args.batch_size is not None and not 1 <= args.batch_size <= 128:
        parser.error("batch_size must be between 1 and 128")
    torch.set_num_threads(1 if args.device == "cpu" else 4)
    set_seed(1337)
    full = args.profile == "full"
    config = GPT2Config(
        vocab_size=50257 if full else 128,
        n_positions=1024 if full else 32,
        n_embd=1024 if full else 32,
        n_layer=24 if full else 2,
        n_head=16 if full else 2,
        resid_pdrop=0.0,
        embd_pdrop=0.0,
        attn_pdrop=0.0,
        use_cache=False,
        bos_token_id=0,
        eos_token_id=1,
        attn_implementation="eager",
    )
    model = GPT2LMHeadModel(config)
    arguments = TrainingArguments(
        output_dir="/tmp/headroom-hf-trainer",
        per_device_train_batch_size=args.batch_size or (16 if full else 2),
        gradient_accumulation_steps=1,
        gradient_checkpointing=False,
        bf16=False,
        fp16=False,
        optim="adamw_torch",
        learning_rate=1e-4,
        lr_scheduler_type="constant",
        max_steps=20,
        seed=1337,
        data_seed=1337,
        full_determinism=True,
        use_cpu=args.device == "cpu",
        dataloader_num_workers=0,
        dataloader_pin_memory=args.device == "cuda",
        save_strategy="no",
        eval_strategy="no",
        report_to=[],
        logging_strategy="steps",
        logging_steps=1,
        disable_tqdm=True,
    )
    print(
        json.dumps(
            {
                "fixture": "hf_trainer",
                "profile": args.profile,
                "pretrained_weights": False,
                "dataset": "deterministic synthetic tokens",
                "seed": 1337,
                "sequence_length": config.n_positions,
                "vocabulary": config.vocab_size,
                "batch_size": arguments.per_device_train_batch_size,
                "acceptance_eligible": full and args.device == "cuda",
            }
        ),
        flush=True,
    )
    trainer = Trainer(
        model=model,
        args=arguments,
        train_dataset=SyntheticTokens(1024, config.n_positions, config.vocab_size, 1337),
    )
    trainer.train()


if __name__ == "__main__":
    main()
