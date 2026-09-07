using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

namespace TokenPet
{
    [Serializable]
    public sealed class RendererCommand
    {
        public string command;
        public string action;
        public string state;
        public string emotion;
        public string slot;
        public string item;
        public bool visible = true;
        public float look_x;
        public float look_y;
    }

    [Serializable]
    public sealed class RendererEvent
    {
        public string event_name;
        public string action;
        public string state;
        public string version;
        public int x;
        public int y;
        public float velocity_x;
        public float velocity_y;
        public string message;
    }

    public sealed class TokenPetIpcClient : MonoBehaviour
    {
        public event Action<RendererCommand> CommandReceived;

        private readonly ConcurrentQueue<RendererCommand> commands = new();
        private readonly object writerLock = new();
        private TcpClient client;
        private StreamReader reader;
        private StreamWriter writer;
        private Thread ioThread;
        private volatile bool stopping;

        public bool IsConnected => client != null && client.Connected;

        private void Awake()
        {
            DontDestroyOnLoad(gameObject);
            int port = ReadPortArgument();
            if (port > 0)
            {
                ioThread = new Thread(() => ConnectAndRead(port))
                {
                    IsBackground = true,
                    Name = "TokenPet Unity IPC"
                };
                ioThread.Start();
            }
        }

        private void Update()
        {
            while (commands.TryDequeue(out RendererCommand command))
            {
                if (command.command == "shutdown")
                {
                    Application.Quit();
                    continue;
                }

                CommandReceived?.Invoke(command);
            }
        }

        public void Send(RendererEvent payload)
        {
            StreamWriter currentWriter = writer;
            if (currentWriter == null)
                return;

            string json = JsonUtility.ToJson(payload);
            try
            {
                lock (writerLock)
                {
                    currentWriter.WriteLine(json);
                    currentWriter.Flush();
                }
            }
            catch (IOException)
            {
                // The Python process owns reconnection/fallback policy.
            }
            catch (ObjectDisposedException)
            {
            }
        }

        private void ConnectAndRead(int port)
        {
            try
            {
                client = new TcpClient();
                client.NoDelay = true;
                client.Connect(IPAddress.Loopback, port);
                NetworkStream stream = client.GetStream();
                reader = new StreamReader(stream, new UTF8Encoding(false));
                writer = new StreamWriter(stream, new UTF8Encoding(false))
                {
                    AutoFlush = true,
                    NewLine = "\n"
                };

                Send(new RendererEvent
                {
                    event_name = "hello",
                    version = "unity-poc-0.1",
                    state = "ready"
                });

                while (!stopping)
                {
                    string line = reader.ReadLine();
                    if (line == null)
                        break;

                    RendererCommand command = JsonUtility.FromJson<RendererCommand>(line);
                    if (command != null && !string.IsNullOrEmpty(command.command))
                        commands.Enqueue(command);
                }
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"TokenPet IPC disconnected: {exception.Message}");
            }
        }

        private static int ReadPortArgument()
        {
            const string prefix = "--tokenpet-port=";
            foreach (string argument in Environment.GetCommandLineArgs())
            {
                if (argument.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) &&
                    int.TryParse(argument.Substring(prefix.Length), out int port))
                {
                    return port;
                }
            }

            return 0;
        }

        private void OnApplicationQuit()
        {
            Send(new RendererEvent { event_name = "renderer_closed", state = "closed" });
            stopping = true;
            try { client?.Close(); } catch { }
            if (ioThread != null && ioThread.IsAlive)
                ioThread.Join(250);
        }
    }
}
