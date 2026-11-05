// Test-only component injected into an isolated copy of the Mono player.
using System;
using System.Collections;
using System.IO;
using System.Reflection;
using UnityEngine;

namespace TokenPet
{
    public sealed class ThrowPhysicsProbe : MonoBehaviour
    {
        private TokenPetPocBootstrap pet;
        private static readonly BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
        private int checks;

        private object Get(string name) => typeof(TokenPetPocBootstrap).GetField(name, Private).GetValue(pet);
        private void Set(string name, object value) => typeof(TokenPetPocBootstrap).GetField(name, Private).SetValue(pet, value);
        private object Call(string name, params object[] args) => typeof(TokenPetPocBootstrap).GetMethod(name, Private).Invoke(pet, args);
        private void Check(bool condition, string message)
        {
            if (!condition) throw new Exception(message);
            checks++;
        }

        private IEnumerator Start()
        {
            yield return new WaitForSecondsRealtime(0.35f);
            string output = Environment.GetEnvironmentVariable("TOKENPET_THROW_PROBE_OUTPUT");
            try
            {
                pet = UnityEngine.Object.FindAnyObjectByType<TokenPetPocBootstrap>();
                Check(pet != null, "bootstrap missing");
                Check(Sample(0).magnitude > 1100f, "ordinary flick lost its velocity");
                Check(Sample(0.2).sqrMagnitude == 0f, "paused drag retained a stale flick");

                // Nonlinear motion must use the Canvas endpoint average,
                // without the previous recency multiplier or 1.5x impulse.
                Vector2[] positions = (Vector2[])Get("throwSamplePositions");
                double[] times = (double[])Get("throwSampleTimes");
                double now = Time.unscaledTimeAsDouble;
                positions[0] = Vector2.zero; times[0] = now - 0.10;
                positions[1] = new Vector2(20, -20); times[1] = now - 0.06;
                positions[2] = new Vector2(100, -60); times[2] = now;
                Set("throwSampleIndex", 2); Set("throwSampleCount", 3);
                Vector2 velocity = (Vector2)Call("ComputeThrowVelocity", new Vector2Int(100, -60));
                Check(Mathf.Abs(velocity.x - 1000f) < 0.1f && Mathf.Abs(velocity.y - 600f) < 0.1f,
                    $"Canvas sample mismatch: {velocity}");

                // At high renderer FPS the ring must retain a full 120 ms.
                for (int i = 0; i < 64; i++)
                {
                    positions[i] = new Vector2(i * 2, 0);
                    times[i] = now - (63 - i) * 0.002;
                }
                Set("throwSampleIndex", 63); Set("throwSampleCount", 64);
                velocity = (Vector2)Call("ComputeThrowVelocity", new Vector2Int(126, 0));
                Check(Mathf.Abs(velocity.x - 1000f) < 0.1f, "high-FPS sampling mismatch");

                TokenPetWindowsOverlay overlay = (TokenPetWindowsOverlay)Get("overlay");
                Call("OnCommand", new RendererCommand { command = "move_window", x = 400, y = 300 });
                Set("pointerDown", true);
                Call("OnCommand", new RendererCommand { command = "move_window", x = 50, y = 60 });
                Check(overlay.GetPosition() == new Vector2Int(400, 300), "Python moved a held pet");
                Set("pointerDown", false); Set("awaitingDragRelease", true); Set("dragId", 4);
                Call("OnCommand", new RendererCommand { command = "drag_release_ack", drag_id = 3 });
                Call("OnCommand", new RendererCommand { command = "move_window", x = 50, y = 60 });
                Check(overlay.GetPosition() == new Vector2Int(400, 300), "stale release ack moved pet");
                Call("OnCommand", new RendererCommand { command = "drag_release_ack", drag_id = 4 });
                Call("OnCommand", new RendererCommand { command = "move_window", x = 450, y = 350 });
                Check(overlay.GetPosition() == new Vector2Int(450, 350), "valid release handoff failed");

                Set("pointerVelocity", new Vector2(2000, 1000));
                Call("OnCommand", new RendererCommand { command = "snapshot", state = "fall", roll_angle = 0 });
                Call("Animate", 1f / 60f);
                Transform motionRoot = (Transform)Get("motionRoot");
                Check(Mathf.Abs(Mathf.DeltaAngle(0, motionRoot.localEulerAngles.z)) < 0.01f,
                    "stationary drop invented a spin from an earlier flick");
                Call("OnCommand", new RendererCommand { command = "snapshot", state = "backflip", roll_angle = 1.25f });
                Call("Animate", 1f / 60f);
                Check(Mathf.Abs(Mathf.DeltaAngle(-1.25f * Mathf.Rad2Deg, motionRoot.localEulerAngles.z)) < 0.01f,
                    "renderer did not follow Canvas angular pose");
                File.WriteAllText(output, $"PASS: {checks} native Unity physics checks");
                Application.Quit(0);
            }
            catch (Exception exception)
            {
                File.WriteAllText(output, exception.ToString());
                Application.Quit(1);
            }
        }

        private Vector2 Sample(double pause)
        {
            Vector2[] positions = (Vector2[])Get("throwSamplePositions");
            double[] times = (double[])Get("throwSampleTimes");
            double now = Time.unscaledTimeAsDouble;
            positions[0] = Vector2.zero; times[0] = now - pause - 0.10;
            positions[1] = new Vector2(100, -60); times[1] = now - pause;
            Set("throwSampleIndex", 1); Set("throwSampleCount", 2);
            return (Vector2)Call("ComputeThrowVelocity", new Vector2Int(100, -60));
        }
    }
}
