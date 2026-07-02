import asyncio
import sys
import os

# Add AI to sys.path so we can import jarvis
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from jarvis.agents.productivity_agent import ProductivityAgent

async def test():
    agent = ProductivityAgent()
    
    # We will mock the LLM chat method to return a python script
    # to test data analytics
    class MockLLM:
        def chat(self, messages):
            return """Here is your code:
```python
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64

df = pd.DataFrame({'Sales': [100, 200, 150]}, index=['Jan', 'Feb', 'Mar'])
fig, ax = plt.subplots()
df.plot(kind='bar', ax=ax)
buf = io.BytesIO()
plt.savefig(buf, format='png')
buf.seek(0)
img_base64 = base64.b64encode(buf.read()).decode('utf-8')
print(f"[IMAGE]data:image/png;base64,{img_base64}[/IMAGE]")
```
"""
    
    print("Testing data analytics mode...")
    result = agent.handle("data analysis", MockLLM(), [])
    print("Result:")
    print(result[:500] + "...")

if __name__ == "__main__":
    asyncio.run(test())
