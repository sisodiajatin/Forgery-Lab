"""Forgery Lab — the Forger. Runs Nous Research's Hermes 3 on a Modal GPU.

Deploy once:   modal deploy modal_forger.py
Smoke test:    modal run modal_forger.py
"""
import modal

MODEL = "NousResearch/Hermes-3-Llama-3.1-8B"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.6.6.post1", "transformers==4.47.1", "tokenizers==0.21.0", "huggingface_hub[hf_transfer]==0.27.1")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
hf_cache = modal.Volume.from_name("forgery-lab-hf-cache", create_if_missing=True)
app = modal.App("forgery-lab-forger", image=image)

SYSTEM = (
    "You are a master literary forger. You study a document's real paragraphs and write a NEW "
    "paragraph that could be slipped into the same document unnoticed: same voice, terminology, "
    "sentence rhythm, citation habits and length. Never copy sentences. Output only the paragraph."
)


@app.cls(gpu="L40S", volumes={"/root/.cache/huggingface": hf_cache}, timeout=900, scaledown_window=120)
class Forger:
    @modal.enter()
    def load(self):
        from vllm import LLM
        self.llm = LLM(MODEL, max_model_len=8192, gpu_memory_utilization=0.9)

    @modal.method()
    def forge(self, context: list[str], topics: list[str], target_words: int = 120) -> list[str]:
        from vllm import SamplingParams
        excerpt = "\n\n".join(context[:6])
        convs = [
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": (
                    f"Real paragraphs from the document:\n\n{excerpt}\n\n"
                    f"Write one new paragraph (~{target_words} words) for this document about: {t}"
                )},
            ]
            for t in topics
        ]
        params = SamplingParams(temperature=0.85, top_p=0.95, max_tokens=int(target_words * 2.2))
        outs = self.llm.chat(convs, params)
        return [o.outputs[0].text.strip() for o in outs]


    @modal.method()
    def chat(self, prompts: list[str], max_tokens: int = 700) -> list[str]:
        """General Hermes-3 calls, used as the case director when the Hermes Agent CLI isn't available (in the cloud)."""
        from vllm import SamplingParams
        convs = [[{"role": "user", "content": p}] for p in prompts]
        outs = self.llm.chat(convs, SamplingParams(temperature=0.7, max_tokens=max_tokens))
        return [o.outputs[0].text.strip() for o in outs]


@app.local_entrypoint()
def main():
    print(Forger().forge.remote(
        ["We propose a new simple network architecture, the Transformer, based solely on attention mechanisms."],
        ["why positional encodings are needed"], 80))
