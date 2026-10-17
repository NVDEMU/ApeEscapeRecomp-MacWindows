package com.nvd123.apeescape;

import android.os.Bundle;
import android.widget.Toast;
import org.libsdl.app.SDLActivity;
import java.io.File;

/** SDL3 host activity. A physical controller is recommended for the dual-stick game. */
public final class GameActivity extends SDLActivity {
    public static final String EXTRA_DISC_PATH = "disc_path";

    @Override
    protected void onCreate(Bundle state) {
        if (getIntent().getStringExtra(EXTRA_DISC_PATH) == null) {
            Toast.makeText(this, "Choose a game image first.", Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        super.onCreate(state);
    }

    @Override
    protected String[] getLibraries() {
        // SDLActivity must load SDL before the game shared library.
        return new String[] { "SDL3", "ApeEscapeRecomp" };
    }

    @Override
    protected String[] getArguments() {
        String disc = getIntent().getStringExtra(EXTRA_DISC_PATH);
        return new String[] {
            "--game", new File(getFilesDir(), "game.toml").getAbsolutePath(),
            "--disc", disc
        };
    }
}
