"""Random-initialized Transformers T5 candidate; no pretrained model or data download."""

import argparse

import torch
from transformers import T5Config, T5ForConditionalGeneration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("full", "cpu-smoke"), default="full")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--steps", type=int, default=20)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("steps must be positive")
    torch.manual_seed(1337)
    tiny = args.profile == "cpu-smoke"
    config = T5Config(
        vocab_size=128 if tiny else 32128,
        d_model=32 if tiny else 768,
        d_kv=16 if tiny else 64,
        d_ff=64 if tiny else 3072,
        num_layers=2 if tiny else 12,
        num_decoder_layers=2 if tiny else 12,
        num_heads=2 if tiny else 12,
        dropout_rate=0.0,
        decoder_start_token_id=0,
        pad_token_id=0,
        eos_token_id=1,
        use_cache=False,
    )
    model = T5ForConditionalGeneration(config).to(args.device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    batch, sequence = (2, 16) if tiny else (4, 512)
    inputs = torch.randint(2, config.vocab_size, (batch, sequence), device=args.device)
    targets = torch.randint(2, config.vocab_size, (batch, sequence), device=args.device)
    for _ in range(args.steps):
        optimizer.zero_grad(set_to_none=True)
        loss = model(input_ids=inputs, labels=targets).loss
        loss.backward()
        optimizer.step()
        print(float(loss.detach()), flush=True)


if __name__ == "__main__":
    main()
