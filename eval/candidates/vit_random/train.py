"""Random-initialized Transformers ViT candidate; no pretrained model or data download."""

import argparse

import torch
from transformers import ViTConfig, ViTForImageClassification


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
    config = ViTConfig(
        image_size=32 if tiny else 224,
        patch_size=8 if tiny else 16,
        num_channels=3,
        hidden_size=32 if tiny else 768,
        num_hidden_layers=2 if tiny else 12,
        num_attention_heads=2 if tiny else 12,
        intermediate_size=64 if tiny else 3072,
        num_labels=10,
        hidden_dropout_prob=0.0,
        attention_probs_dropout_prob=0.0,
    )
    model = ViTForImageClassification(config).to(args.device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    batch = 2 if tiny else 8
    images = torch.randn(batch, 3, config.image_size, config.image_size, device=args.device)
    labels = torch.arange(batch, device=args.device) % config.num_labels
    for _ in range(args.steps):
        optimizer.zero_grad(set_to_none=True)
        loss = model(pixel_values=images, labels=labels).loss
        loss.backward()
        optimizer.step()
        print(float(loss.detach()), flush=True)


if __name__ == "__main__":
    main()
